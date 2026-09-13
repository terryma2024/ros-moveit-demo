# SO-101 parallel multi-point validation experiment ledger

```yaml
task_id: so101-parallel-multipoint-validation-20260912-v1
goal: Implement and qualify isolated MuJoCo workers with dynamic point leasing across the frozen 20-point catalog.
success_contract: One immutable execute batch physically passes all 20 catalog points with qualification_passed=true and all evidence, isolation, recovery, and cleanup gates satisfied.
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
branch: codex/so101-parallel-multipoint-validation
base_commit: 5bfc5dbe7a7a92448f6e89a9a262b82117dec0a5
current_commit: daec04aaaa91825c480d4513d29f93e7c975c303
current_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1
confirmed_conclusions:
  - The dispatch receipt and frozen plan, design, and point catalog hashes were verified before implementation (CP-001).
  - The canonical checkout remains at the expected base with only its pre-existing .gitignore change (CP-001).
  - The implementation worktree initially used the clean mujoco_ros2_control gitlink 71bc9346cf93d6227a6678fcacf63f3e18acfcba at CP-001; the current reviewed and qualified gitlink is c16b5a5fe880b6e1857f56486dab4ae726576969 (EXP-095).
  - The shared detector runtime is review-clean; its content-verified immutable image executed both frozen models successfully on the frozen P01 RGB (CP-008, EXP-007, EXP-008).
  - Isolated Worker resource admission is review-clean; EXP-017 admitted exactly two process-free Worker resource sets and left no owned process, container, or GPU task (CP-009).
  - The Worker state machine is review-clean with deadline-bounded authorization RPCs, mode-specific durable start evidence, local sealing before commit, and atomic deadline-bound recovery/readmission (CP-010).
  - The isolated Worker runtime is review-clean with headless launch constraints, strict owned-process identity, mode-separated execution, attempt-bound fresh visual/numeric evidence, and replacement-backed process generations (CP-011).
  - The authenticated coordinator CLI is review-clean with exact Worker/Broker IPC, process-tree cleanup, source-clock pose admission, artifact composition, and stale-overlay rejection (CP-012).
  - Crash-window and Broker-recovery behavior is review-clean; abnormal terminal reasons cannot produce successful batch or validation outcomes (CP-013).
  - The fresh three-package overlay, complete ordinary package gate, installed provenance, and immutable dual-model Broker image are qualified for live validation (CP-014, EXP-022).
  - F35 preserves bounded Worker initialization diagnostics and closes the supervised-exit observation race without weakening absent-process or PID-reuse rejection; the complete ordinary gate and rebuilt immutable image passed (CP-015).
  - F36 retries idempotent paused snapshots for volatile subscribers, serializes Worker cleanup publication, and boundedly observes an exiting exact child; the complete ordinary gate and rebuilt immutable image passed (CP-016).
  - F37 retains exactly the latest authoritative atomic MuJoCo evidence with matching reliable transient-local QoS, so a strict late observer receives the paused reset watermark; affected-package gates and the rebuilt immutable image passed (CP-017).
  - F38 uses the authoritative ROS action-status QoS for the point-initial no-active-goal observations; its complete ordinary gate and rebuilt immutable image passed (CP-018).
  - F39 preserves the point-initial conjunction while emitting bounded missing-class diagnostics; its complete ordinary gate and rebuilt immutable image passed (CP-019).
  - F40 carries the reset transaction's already-validated six-joint sample across the reset boundary and uses completed all-goal CancelGoal responses as positive no-active-goal evidence; its complete ordinary gate and rebuilt immutable image passed (CP-020).
  - F41 preserves every point-initial predicate while reporting a bounded fixed-order rejected-predicate list; its complete ordinary gate and rebuilt immutable image passed (CP-021).
  - F46 tolerates only the bounded child-side setsid observation race, while persistent incomplete or foreign identities remain fail-closed and receive no process-group signal; its complete ordinary gate and rebuilt immutable image passed (CP-026).
  - F47 binds the already-validated production point-initial facts to all seven exact lease identity fields before the Worker's unchanged authorization check; its complete ordinary gate and rebuilt immutable image passed (CP-027).
  - EXP-044 proved the F47 gate receipt is correct but exposed the complementary production reset-receipt identity omission before ATTEMPT_STARTED; F48 is limited to binding that reset receipt to the same seven exact lease fields (CP-028).
  - F48 binds the production reset receipt to all seven exact lease identity fields while preserving reset and Worker gate semantics; its fresh complete ordinary gate and immutable dual-model image passed (CP-029).
  - EXP-045 crossed both exact lease-bound reset/gate receipts and durable ATTEMPT_STARTED, then exposed deterministic insecure-mode rejection in Broker input mirror intermediates; F49 preserves the Broker security gate and fixes the producer path modes (CP-030).
  - F50 preserves conservative authorization-failure semantics while exposing bounded phase/type/message diagnostics; its fresh complete ordinary gate and immutable dual-model image passed (CP-033).
  - EXP-047 separated one transient initial graph rejection from one successful Broker RPC returning model INFRA_ERROR; F51 is limited to preserving the Broker response reason in bounded Worker diagnostics (CP-034).
  - F51 preserves Broker infrastructure outcome/reason in bounded Worker diagnostics without changing perception or attempt results; its fresh complete ordinary gate and immutable dual-model image passed (CP-035).
  - EXP-048 proved both Workers reach the authenticated Broker with exact lease-bound evidence, and isolated BROKER_NOT_READY to a missed ready callback when an already-started healthy runtime is attached to PerceptionService; F52 is limited to replaying that lifecycle state (CP-036).
  - F52 replays ready state only for an already-started healthy runtime, without rebuilding detectors or rewriting receipts; its complete ordinary gate and rebuilt immutable dual-model image passed (CP-037).
  - EXP-049 stopped before admission because the verified worktree libexec was absent from PATH; EXP-050 repeats with only that previously validated environment binding (CP-038).
  - EXP-050 proved F52 Broker readiness and one complete physical PASS, then exposed a `/cup_pose` publication race against the new consumer node's uninitialized simulation clock; F53 synchronizes publication to the accepted source stamp without relaxing pose freshness (CP-039).
  - EXP-046 proves F49 creates the complete production Broker mirror chain as exact 0700, but the unchanged Worker result projection hides the next immediate request-layer exception; F50 adds bounded post-authorization phase diagnostics only (CP-032).
  - F49 creates and verifies every Broker input mirror directory as an exact owner-only 0700 directory; its complete ordinary gate and rebuilt immutable dual-model image passed (CP-031).
  - EXP-088 validly proved the historical plan-only exact Worker and Broker TERM recovery gate with no lease grant during Broker unhealth and physical action proven absent.
  - EXP-094 validly passed the final F91 four-point execute qualification, and immutable historical EXP-095 validly passed all 20 frozen points with qualification_passed=true.
  - Astra findings 1 through 7 are confirmed and fixed at CP-089; their focused and adjacent gates pass, while rebuilt-overlay and live qualification remain pending.
  - EXP-118 proves the repaired heartbeat watchdog independently retires the exact direct consumer by the first six-second observation and submits no controller goal after watchdog expiry while Coordinator-dependent Broker fencing remains blocked; the interrupted attempt remains conservatively INDETERMINATE (CP-105).
disproven_routes:
  - The canonical install overlay is not usable for this task because setup.zsh references stale external overlays (CP-001).
open_hypotheses:
  - EXP-096 confirmed Astra finding 1 and the candidate now performs exact-lease cancel-and-confirm outside the blocked execution lock; post-commit package and live fault evidence remain pending.
  - EXP-097 confirmed Astra finding 2 and the candidate now propagates authenticated exact-generation health loss and replaces a live unhealthy Broker; package and live fault evidence remain pending.
  - EXP-098 confirmed Astra finding 3 and the candidate now continues after a durably committed, successfully recovered initial-gate INVALID without hiding its diagnostic.
  - EXP-099 confirmed Astra finding 4 and the candidate now verifies exact dynamic terminal identity and reached-stage evidence before classifying PASSED or FAILED.
  - Astra finding 8 is confirmed by the stale recovery header and is being synchronized under EXP-103; final package and live qualification remain pending.
latest_checkpoint: CP-107
next_experiment: EXP-121
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
- Ruling F37: Task 14 returns narrowly to the repository-owned atomic MuJoCo evidence publisher and Python observer QoS seams, with their direct tests. The 100 Hz atomic evidence topic must retain exactly its newest sample with reliable transient-local durability, and the strict observer must request matching depth-1 reliable transient-local durability. This gives a late-joining post-reset observer the already-published authoritative paused frame without unpausing, stepping, weakening freshness/session/sequence checks, or changing the pinned third-party MuJoCo service implementation. Existing volatile sensor-data consumers remain compatible with the stronger publisher offer. Cost if wrong: stale history could be mistaken for current evidence, which the existing max-age/session/epoch checks must reject; retaining volatile/volatile QoS makes the documented current_evidence late-join contract impossible, as EXP-031 proved.
- Ruling F38: Task 14 returns narrowly to the production point-initial observation and its direct tests. The three late-created action-status subscriptions must request ROS 2's exact `qos_profile_action_status_default` (keep-last depth 1, reliable, transient-local), matching the action servers and receiving their retained empty status arrays when no goal has ever run. The observed reset, joint, scene, contact, graph, freshness, and exact-node gates remain unchanged. Cost if wrong: a stale status sample could be admitted, but the retained action status is the authoritative current status set and active goal IDs are still enumerated conservatively; retaining volatile subscriptions makes an empty never-used action server indistinguishable from an absent observation and produced the identical dual-Worker timeout in EXP-032.
- Ruling F39: Before changing any remaining point-initial observation semantics, make the existing bounded timeout diagnostic enumerate only the missing observation classes: fresh canonical joint callback, exact action-status topic receipts, completed planning-scene response, and stable graph samples. Keep the timeout, gate conjunction, values, and fail-closed behavior unchanged, add direct RED/GREEN coverage, then run one fresh unchanged execute to identify the actual missing class. Cost if wrong: diagnostics could become unbounded or leak payloads; retaining the opaque timeout forces further speculative changes after EXP-033 proved F38 necessary but insufficient.
- Ruling F40: Task 14 may replace the impossible post-pause joint/status waits with equivalent authoritative evidence, with direct contract and runtime tests. The successful reset transaction must return the exact fresh post-reset six-joint sample that it already requires before re-pausing; point-initial gate must consume that bound sample, never synthesize canonical values. For no-active-goal proof, issue an all-goals CancelGoal query to each isolated action server before authorization and require completed responses with no goals_canceling; any returned goal ID fails the gate. Planning-scene, contact, reset/session, graph, node-identity, freshness, timeout, and pre-authorization motion prohibitions remain unchanged. Cost if wrong: cancellation could mutate a stale active goal, but that condition still fails authorization and is safer than permitting it; retaining fresh subscribers after physics is paused and before any goal exists is unobservable by construction, as EXP-034 proved on both Workers.
- Ruling F41: Before changing any remaining point-initial predicate, replace the opaque aggregate rejection with a bounded fixed-order list of failed predicate names covering type, reset identity, freshness, joints, goals, attachment, contact, graph stability, and exact node set. Preserve the conjunction and all values unchanged, add direct RED/GREEN coverage, then repeat the unchanged execute. Cost if wrong: diagnostic text could be mistaken for authorization logic; therefore tests must prove it changes only failure attribution and no predicate is removed.
- Ruling F42: Task 14 may narrowly correct the two point-initial observation mappings identified by EXP-037, with direct RED/GREEN tests. The forbidden-contact predicate must be true only when either fingertip-contact collection is nonempty; legal table/support contact in the broad atomic evidence must not fail this predicate. The exact stable Worker-node inventory must include the three required active controller nodes `/arm_controller`, `/gripper_controller`, and `/joint_state_broadcaster` while continuing to reject any missing, duplicate, or unknown node. Reset/session, freshness, joints, goals, attachment, graph stability, all physical thresholds, and all downstream authorization remain unchanged. Cost if wrong: an actual fingertip contact or stale node could pass; therefore tests must prove fingertip rejection and exact-inventory rejection independently.
- Ruling F43: Before changing the exact Worker-node inventory again, extend only the existing bounded `worker_nodes` rejection diagnostic to report deterministic expected, missing, and unexpected FQNs. Each collection is sorted, length bounded by the frozen graph limit, and contains only already-observed node names; duplicate observations remain rejected and are reported separately by a bounded duplicate list. The equality predicate and every authorization value remain unchanged. Cost if wrong: diagnostic payload could become unbounded; direct tests must prove ordering, bounds, duplicate attribution, and unchanged acceptance/rejection.
- Ruling F44: Compress the F43 node diagnostic so the complete payload, including the fixed failure prefix, fits the existing 512-byte Worker failure-message contract for the observed graph. Omit the redundant full expected list; retain sorted `missing`, `unexpected`, `duplicates`, and `truncated`, with the same per-list and per-name bounds. Add a direct integration assertion through `_bounded_failure_message` proving no truncation for the bounded payload. Equality and authorization remain unchanged. Cost if wrong: another diagnostic run remains inconclusive; increasing the Worker failure bound or weakening graph admission is not authorized.
- Ruling F45: Replace impossible whole-graph tuple equality with an exact stable topology predicate that matches the independently observed two-Worker graph and the design's actual stale-node isolation requirement. Require every fixed Worker node exactly once; require the four legitimate fixed internal nodes `/controller_manager`, `/move_group/moveit`, `/moveit_simple_controller_manager`, and `/robotsystem` exactly once; require exactly one node in each runtime-generated category `/move_group_private_<decimal>`, `/moveit_<decimal>`, and `/transform_listener_impl_<lower-hex>`. Reject any missing node, duplicate FQN, second member of a generated category, malformed suffix, or unknown node. Keep stable-graph sampling and all non-node gates unchanged. Cost if wrong: an old in-domain internal node could be admitted; direct tests must cover missing, duplicate-category, malformed, and unknown-node rejection before live execution.
- Ruling F46: ProcessSupervisor.start may boundedly retry `/proc` identity reads for an alive exact Popen child while its `start_new_session=True` setsid transition is not yet visible. Retry at most eight reads with a 1 ms yield; admit only a complete identity with pgid==pid. If the child exits or never becomes a self-led group, preserve CHILD_IDENTITY, reap the exact Popen child, and never signal a foreign/unverified group. PID reuse, command/start-time identity, manifest durability, and shutdown semantics remain unchanged. Cost if wrong: a foreign group could be signalled; direct RED/GREEN tests must prove transient inherited-PGID success and persistent foreign-PGID no-signal failure.
- Ruling F47: `ParallelRosRuntime.initial_gate` must bind its already-validated point-initial facts to the exact current lease by copying the seven immutable lease identity fields into the returned gate receipt. It may not synthesize, normalize, or omit identity, and `ParallelWorker._gate_summary` retains exact type-and-value checks against both reset and gate receipts before ATTEMPT_STARTED. Cost if wrong: evidence from another point, generation, or Worker could authorize execution; direct RED/GREEN tests must prove all seven production fields and preserve mismatch rejection.
- Ruling F48: `ParallelRosRuntime.reset_point` must bind its validated reset boundary to the exact current lease by copying the same seven immutable identity fields into `ResetBoundaryReceipt`. Standalone observation-only receipt construction remains compatible, but production authorization still requires exact type and value on both reset and gate receipts. Cost if wrong: a reset from another lease could authorize inference; direct RED/GREEN tests must exercise the production reset path.
- Ruling F49: Broker input mirroring must create every directory below the already-private `broker-inputs` root sequentially with exact mode 0700 and verify owner, type, mode, and no symlink before linking the immutable 0400 RGB file. `Path.mkdir(parents=True, mode=0700)` is insufficient because intermediate directories inherit umask-derived 0775 and the Broker correctly rejects them. Do not relax `ParallelPerceptionRuntime._frame` or its read-only/owner/mode/hash checks. Cost if wrong: group-writable path substitution could reach the privileged CUDA Broker; direct RED/GREEN must force umask 0002 and prove every mirrored parent is 0700.

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

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-022
current_hypothesis: The F37-matched reliable transient-local evidence channel lets each post-reset strict observer receive the already-published authoritative paused watermark without advancing physics.
working_tree_status: clean at source commit 87e1f97e58bbe3e45e0a058f219f44f4e8513629 before the EXP-032 ledger-only pre-run commit
owned_processes: NONE; the F37 smoke container exited and no task container or NVIDIA compute application remains
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Python RED pytest-eb6fdBjp failed the new late-observer contract at depth 5 versus required depth 1; focused GREEN pytest-5UxN4rlU and repeat pytest-04Q9pjMe each passed 3/3.
  - Formal C++ RED p41 failed the late-join test with exact DURABILITY_QOS_POLICY incompatibility and zero retained messages; focused GREEN p43 passed 1/1 and full support p44 passed 21/21.
  - The publisher and strict observer now both use depth-1 reliable transient-local QoS. Existing freshness, source-session, reset-epoch, simulation-time, and sequence checks remain unchanged.
  - Fresh p45 rebuilt so101_mujoco_support, so101_teleop, and so101_demo_py in 1.97 s. Its combined test command retained an unrelated so101_teleop collection failure because the system interpreter lacks pydantic v2 field_validator; affected support and demo packages passed. Fresh p46 then passed the complete affected-package gates in 84.44 s: support 21 tests and demo 2766 tests, with 0 errors, 0 failures, and 0 skipped; benchmark_test was not collected.
  - Installed source/build module trees are equal at SHA256 6042870147e0f3e5dd9e10c6133966e4cf8e7e3224916a6e4cd583942d02a3ee; the complete demo source tree is SHA256 42f3e2f0f8359c7dcc1d9cef723ee26ae93c03e9f9482a25dcc492872d4a6af2.
  - Rebuilt immutable image sha256:21287879104568e1ce1877eff4d8b5ca07bc6943fdf8f1e4eea838e9307eab52 binds equal source/verified SHA256 42f3e2f0f8359c7dcc1d9cef723ee26ae93c03e9f9482a25dcc492872d4a6af2. Fresh smoke returned one QUALIFIED CUDA candidate from each frozen model and left no container/GPU process.
  - Fresh EXP-032 preflight found no related process, container, GPU task, or ROS domain 181-183 owner; 24 CPUs, 25.858 GiB MemAvailable, and 14.914 GiB free GPU exceed admission.
disproven_routes:
  - Best-effort transient-local did not deliver historical Fast DDS data to a reliable late subscriber; the repository-owned publisher must offer reliable durability matching the strict observer.
  - Retrying an already-paused SetPause request cannot trigger the pinned third-party snapshot hook, because that implementation returns before dispatch on an idempotent request.
open_risks:
  - No four-point execute has yet reached ATTEMPT_STARTED, so controlled fault and 20-point admission remain closed until EXP-032 is accepted.
next_command: Execute the clean pre-registered EXP-032 two-Worker four-point batch using image sha256:21287879104568e1ce1877eff4d8b5ca07bc6943fdf8f1e4eea838e9307eab52.
```

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-022
current_hypothesis: The F38-corrected initial gate receives each action server's retained authoritative empty status array and can cross ATTEMPT_STARTED without weakening no-active-goal evidence.
working_tree_status: clean at source commit 1bed539ab6766e78c60f6f9ca1a68487ac06921c before the EXP-033 ledger-only pre-run commit
owned_processes: NONE; no task container or NVIDIA compute application remains
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Formal behavioral RED pytest-oI97UFfw reached the production observation and captured integer QoS 10 for all three action-status subscriptions instead of the authoritative ROS default. pytest-OntkKPCB is retained as a test-authoring failure, while pytest-39IkkUAJ and pytest-bWdK1CUZ retain implementation import-placement failures.
  - Final focused pytest-VEilHhNY passed the full parallel_ros_runtime file 14/14, and adjacent pytest-6mRrcnHi passed 154/154 across ROS runtime, Worker runtime, and Worker state-machine tests.
  - The production point-initial gate now requests exactly `qos_profile_action_status_default` for all three late-created subscriptions; all reset, joint, scene, contact, graph, node-identity, and freshness checks remain unchanged.
  - Fresh p47 symlink build completed in 1.50 s and the complete ordinary demo suite passed in 83.45 s: 2767 tests, 0 errors, 0 failures, 0 skipped; benchmark_test was not collected.
  - Installed source/build module trees are equal at SHA256 cbfa195e5887e13852afc0cd0f4a94474a1be37eba3d49c307ea550c925a5e4d; complete demo source tree is SHA256 d1b0dec9ea54047d9f1bc477f5df5decec57b7013cf45c88f5469fc2c30ab1c2.
  - Rebuilt immutable image sha256:6a0a9744a4773e0bfdaf5fd2127a073d0043aa2988c2fed074e7da520a523ebd binds equal source/verified SHA256 d1b0dec9ea54047d9f1bc477f5df5decec57b7013cf45c88f5469fc2c30ab1c2. Fresh smoke returned one QUALIFIED CUDA candidate from each frozen model and left no container/GPU process.
  - Fresh EXP-033 preflight found no related process, container, GPU task, or ROS domain 181-183 owner; 24 CPUs, 25.782 GiB MemAvailable, and 14.914 GiB free GPU exceed admission.
disproven_routes:
  - A reliable but volatile subscription does not receive a transient-local action server's retained empty status sample when no goal has ever run; integer depth 10 cannot prove the no-active-goal gate.
open_risks:
  - No four-point execute has yet reached ATTEMPT_STARTED, and EXP-032 required external exact-container cleanup on its abnormal terminal path.
next_command: Execute the clean pre-registered EXP-033 two-Worker four-point batch using image sha256:6a0a9744a4773e0bfdaf5fd2127a073d0043aa2988c2fed074e7da520a523ebd.
```

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-022
current_hypothesis: Bounded class-specific F39 evidence will identify the remaining absent point-initial observation without altering the gate.
working_tree_status: clean at source commit 9998277763bfe78b77d3fa798909111ad576f135 before the EXP-034 ledger-only pre-run commit
owned_processes: NONE; no task container or NVIDIA compute application remains
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Formal diagnostic RED pytest-OgDzg6sz proved the existing timeout omitted the sole missing joint-state class; the preceding pytest-VBy9e3oz is retained as a test-authoring failure.
  - Final adjacent GREEN pytest-gOX2JA6z passed 154/154. The timeout now lists only fixed missing-class identifiers and retains the exact original conjunction and timeout.
  - Fresh p48 symlink build completed in 1.49 s and the complete ordinary demo suite passed in 84.12 s: 2767 tests, 0 errors, 0 failures, 0 skipped; benchmark_test was not collected.
  - Installed source/build module trees are equal at SHA256 839b762488969c3e0a79ae551953be79cdb68d9c07f2290c592348cb018e5b85; complete demo source tree is SHA256 2a99e1fc82cca5f8818f7731db507683f403a4e2ddfe4b6303b7a8ab1078e5d4.
  - Rebuilt immutable image sha256:35da277058a9dba01ef0ad7073c227d31597c38b3fa0cad2a61e47b500b23f64 binds the same source hash. Fresh smoke returned one QUALIFIED CUDA candidate per frozen model and left no container/GPU process.
  - Fresh EXP-034 preflight found no related process, container, GPU task, or ROS domain 181-183 owner; 24 CPUs, 25.749 GiB MemAvailable, and 14.911 GiB free GPU exceed admission.
open_risks:
  - The remaining initial-gate missing class is not yet known; EXP-034 must not be interpreted as a physical point attempt unless ATTEMPT_STARTED is reached.
next_command: Execute clean pre-registered diagnostic EXP-034 using image sha256:35da277058a9dba01ef0ad7073c227d31597c38b3fa0cad2a61e47b500b23f64.
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
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T17:31:22+08:00
  - status: RUNNING
    at: 2026-09-12T17:31:22+08:00
  - status: INVALID
    at: 2026-09-12T17:35:21+08:00
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
    exit_code: 1
observed:
  - Admission and immutable Broker startup passed. Both isolated stacks reached READY, but startup skew meant only worker-02 leased task_start before the invalidating initialization failure; no ATTEMPT_STARTED event exists and all four points remain UNRUN.
  - worker-02 retained failure_boundary=reset_point, failure_type=RuntimeError, and failure_message="fresh paused atomic MuJoCo evidence unavailable". worker-01 received the authenticated stop before leasing and retained WORKER_NOT_READY.
  - The F36 repeated pause requests all succeeded as already-paused no-ops. Repository source readback proves the pinned third-party service returns before observer_dispatcher.on_state_snapshot when currently_paused equals the request, so no number of retries can publish a frame.
  - The repository-owned evidence publisher and Python observer both use volatile sensor-data QoS. The authoritative paused frame did publish during reset, but a new post-reset observer has no retained sample to receive. This directly contradicts current_evidence's late-join contract.
  - F36 cleanup behavior passed its live purpose: neither Worker had a manifest temporary collision, the supervisor produced no OWNED_PROCESS_ABSENT traceback, and final external readback found empty ownership manifests, no exact Broker container, no GPU compute application, and no node in domains 181-183.
inferred:
  - This remains an initialization/evidence-delivery defect before physical authorization, not a trustworthy point outcome. A matching depth-1 transient-local publisher/subscriber pair is the narrow repository-owned fix; freshness, session, reset-epoch, and sequence checks still fence historical misuse.
conclusion: INVALID; zero countable attempts. Apply F37 with Python and C++ RED/GREEN evidence, fresh three-package build/test, ordinary package gate, installed provenance, rebuilt immutable image, fresh dual-model smoke, and repeat the unchanged four-point execute under EXP-032.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p39
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f36.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f36.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f36-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-031.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-031.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-031.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f36/coordinator/events/segment-00000000000000000001.journal
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f36/coordinator/aggregate_results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f36/workers/worker-01/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f36/workers/worker-02/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-031-cleanup-audit.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP031.txt
hashes:
  live_command_log_sha256: cbe38c9016f1094fe559ee92e842dfba11b59612c141535ceec5f0af3b535ad0
  journal_sha256: f08f4b9f288f9bb7553b4fd07f5596176a16ec97219fdeb5552175fd2f62faab
  coordinator_aggregate_sha256: a1d5bd576827efadc3bb016a6b76d0589aafa69f0371af93dfede1cccedf626e
  worker_01_result_sha256: be7278bf3c0df75b24dbaf98581c69670cac2b89297d629c68ec6e44597c1945
  worker_02_result_sha256: dd5291bb844a798b5ffcbe6588911d3c68608443c1c9173bc4d284f802da9695
  cleanup_audit_sha256: cb90f18fd2d696b032950c09c702e9eafc74faf30abd13bd3fe02d645e2c94b6
  mujoco_warning_log_sha256: cc7019d51be45b6373f444b0845c64d6ad4e18d4f57aa9bd9c62ebbda67e99ec
retained: complete live-small-f36 tree, command/preflight/cleanup reports, journal/projections, Worker diagnostics, ROS logs, container cidfile, and relocated MuJoCo warning log
archived: none
deletion_candidates: scratch p38/p39 and direct-pytest scratch remain candidates; nothing was deleted
decision: REPEAT after F37 RED/GREEN, fresh three-package and ordinary package gates, installed provenance, image rebuild, and dual-model smoke
next_experiment: EXP-032 is reserved for the F37-corrected execute repeat; controlled plan-only fault advances to EXP-033 and remains blocked until execute acceptance
```

## EXP-032 — Task 14 retained-evidence two-Worker execute

```yaml
experiment_id: EXP-032
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T17:48:00+08:00
  - status: RUNNING
    at: 2026-09-12T17:48:00+08:00
  - status: INVALID
    at: 2026-09-12T17:51:47+08:00
prior_experiment: EXP-031
hypothesis: F37 delivers the authoritative paused reset watermark to every new strict observer, allowing the otherwise unchanged four-point execute to cross durable point authorization and complete physical evaluation.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass.
single_variable: F37 changes only the repository-owned atomic evidence publisher and observer to matching depth-1 reliable transient-local QoS. Selection, configuration, models, N=2, K=2, and physical criteria remain frozen; source/install/image and batch/root identities advance because code changed and prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f37
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f37
preconditions:
  - F37 Python and C++ behavioral RED/GREEN passed; p44 passed all 21 support tests and p46 passed support 21 plus demo 2766 with no error/failure/skip and no benchmark collection.
  - Installed source/build module trees both hash SHA256 6042870147e0f3e5dd9e10c6133966e4cf8e7e3224916a6e4cd583942d02a3ee.
  - Immutable image sha256:21287879104568e1ce1877eff4d8b5ca07bc6943fdf8f1e4eea838e9307eab52 binds equal source/verified SHA256 42f3e2f0f8359c7dcc1d9cef723ee26ae93c03e9f9482a25dcc492872d4a6af2 and passed fresh dual-model smoke.
  - Fresh inventory and production probe found no related stack process, container, GPU task, or domain 181-183 owner; live-small-f37 is absent.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
  - Exact labeled Broker cid is absent after shutdown and aggregate cleanup is true only with no process/container/GPU residue.
failure_criteria:
  - Trustworthy initialized product behavior fails a physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, evidence pollution, or an initial boundary failure before ATTEMPT_STARTED prevents trustworthy behavior counting.
provenance:
  executable_source_commit: 87e1f97e58bbe3e45e0a058f219f44f4e8513629
  executable_source_tree: 42f3e2f0f8359c7dcc1d9cef723ee26ae93c03e9f9482a25dcc492872d4a6af2
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:21287879104568e1ce1877eff4d8b5ca07bc6943fdf8f1e4eea838e9307eab52
  image_source_sha256: 42f3e2f0f8359c7dcc1d9cef723ee26ae93c03e9f9482a25dcc492872d4a6af2
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: fresh stack inventory and production domain/resource probe to reports/process-inventory-before-032.json and reports/domain-preflight-before-032.json
    exit_code: 0
  - command: prepend verified worktree libexec, then run the frozen four-point ros2 execute with fresh EXP-032 batch/root and reports/live-small-command-032 log/exit/time evidence
    exit_code: 1
observed:
  - F37 succeeded at its intended boundary: neither Worker reported fresh paused atomic evidence unavailable. Both isolated stacks reached READY, reset their distinct first leased point, and remained before ATTEMPT_STARTED.
  - Both Workers then retained the identical exact diagnostic failure_boundary=point_initial_gate, failure_type=RuntimeError, failure_message=POINT_INITIAL_GATE_OBSERVATION_TIMEOUT. The journal has two leases/ACKs and no ATTEMPT_STARTED event; all four points remain UNRUN and zero outcomes are countable.
  - Production code creates three action-status subscriptions only after reset, using integer QoS depth 10, which means reliable but volatile. ROS Jazzy's authoritative action status publisher default is keep-last depth 1, reliable, transient-local. With no action goal yet, its retained empty status array is the only positive no-active-goal observation; each new volatile subscriber can miss it and the gate waits forever for all three goal_receipts.
  - Both failed recovery replacement launches were stopped conservatively and Workers became QUARANTINED. The coordinator ended CAPACITY_EXHAUSTED. Aggregate cleanup correctly remained false because the detached exact Broker container survived the controller outcome.
  - External cleanup verified the cidfile, batch/generation labels, immutable image, and batch-specific mounts before stopping only that exact container. Independent audit2 then found empty ownership manifests, no matching process/container/GPU task, and no domain 181-183 owner. The first cleanup log is retained but its pgrep result is inspection-command self-matching and is not used.
inferred:
  - This is another late-join observation defect before physical authorization, not a trustworthy point outcome. Matching the action clients' own ROS-default status QoS is the narrow fix and does not weaken any gate.
  - Controller cleanup still has a separate abnormal-terminal Broker retirement defect: the correct false aggregate prevented a false pass, but an externally verified exact-container stop was required.
conclusion: INVALID; zero countable attempts. Apply F38 with behavioral RED/GREEN and affected-package gates, rebuild provenance/image, repeat smoke, and then repeat the unchanged four-point execute under EXP-033. Keep Broker abnormal-terminal retirement on the next live readback gate.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p41
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p43
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p44
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p46
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-eb6fdBjp.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-5UxN4rlU.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f37.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f37.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f37-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-032.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-032.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-032.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f37/coordinator/events/segment-00000000000000000001.journal
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f37/coordinator/aggregate_results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f37/workers/worker-01/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f37/workers/worker-02/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-032-cleanup-audit2.json
hashes:
  live_command_log_sha256: 0e769922eb0de289ecb7847106ba8db2b3d7598335035a0c3a8ccc2525201d4c
  journal_sha256: 37d0d853127462f1bf5b6f6684143166ab24a7b361a033d6cffdeaad69de0650
  coordinator_aggregate_sha256: 6569a3cf1c50309e68157723d0757a3b993ed4eed50bc30ae95fb41b40afef87
  worker_01_result_sha256: 6bd757d95103569f98cdef5d34d506c5e20d9ab6642b58e5cf3e96884e20b59b
  worker_02_result_sha256: a4b821144eb6814b8befc2521a87a3adb80967b8fff06f02b31d25d0d1ec6e03
  cleanup_audit_sha256: 63122ec3494857e52a452cb859fc773cacecc23a0f37dae6b8c60eda724d70ca
retained: complete live-small-f37 tree, command/preflight/cleanup reports, journal/projections, Worker diagnostics, ROS logs, container cidfile, and all F37 test/build/image/smoke evidence
archived: none
deletion_candidates: p40 through p46 and direct-pytest scratch are candidates after readback; nothing was deleted
decision: REPEAT after F38 RED/GREEN, affected-package gate, installed provenance, image rebuild, and dual-model smoke
next_experiment: EXP-033 is reserved for the F38-corrected execute repeat; controlled plan-only fault advances to EXP-034 and remains blocked until execute acceptance
```

## EXP-033 — Task 14 action-status-corrected two-Worker execute

```yaml
experiment_id: EXP-033
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T18:02:00+08:00
  - status: RUNNING
    at: 2026-09-12T18:02:00+08:00
  - status: INVALID
    at: 2026-09-12T18:04:58+08:00
prior_experiment: EXP-032
hypothesis: F38 lets the point-initial gate receive each action server's retained authoritative empty status array, allowing the otherwise unchanged execute batch to cross ATTEMPT_STARTED and complete four physical evaluations.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass.
single_variable: F38 changes only the three point-initial action-status subscriptions to ROS 2's exact action-status default QoS. Selection, configuration, models, N=2, K=2, and physical criteria remain frozen; source/install/image and batch/root identities advance because code changed and prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f38
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f38
preconditions:
  - F38 behavioral RED/GREEN passed, adjacent gate passed 154 tests, and p47 complete ordinary demo gate passed 2767 tests with no error/failure/skip and no benchmark collection.
  - Installed source/build module trees both hash SHA256 cbfa195e5887e13852afc0cd0f4a94474a1be37eba3d49c307ea550c925a5e4d.
  - Immutable image sha256:6a0a9744a4773e0bfdaf5fd2127a073d0043aa2988c2fed074e7da520a523ebd binds equal source/verified SHA256 d1b0dec9ea54047d9f1bc477f5df5decec57b7013cf45c88f5469fc2c30ab1c2 and passed fresh dual-model smoke.
  - Fresh inventory and production probe found no related stack process, container, GPU task, or domain 181-183 owner; live-small-f38 is absent.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
  - Exact labeled Broker cid is absent after shutdown and aggregate cleanup is true only with no process/container/GPU residue.
failure_criteria:
  - Trustworthy initialized product behavior fails a physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, evidence pollution, or an initial boundary failure before ATTEMPT_STARTED prevents trustworthy behavior counting.
provenance:
  executable_source_commit: 1bed539ab6766e78c60f6f9ca1a68487ac06921c
  executable_source_tree: d1b0dec9ea54047d9f1bc477f5df5decec57b7013cf45c88f5469fc2c30ab1c2
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:6a0a9744a4773e0bfdaf5fd2127a073d0043aa2988c2fed074e7da520a523ebd
  image_source_sha256: d1b0dec9ea54047d9f1bc477f5df5decec57b7013cf45c88f5469fc2c30ab1c2
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: fresh stack inventory and production domain/resource probe to reports/process-inventory-before-033.json and reports/domain-preflight-before-033.json
    exit_code: 0
  - command: prepend verified worktree libexec, then run the frozen four-point ros2 execute with fresh EXP-033 batch/root and reports/live-small-command-033 log/exit/time evidence
    exit_code: 1
observed:
  - The exact F38 code and image admitted cleanly. worker-02 leased task_start, reset successfully, and then retained failure_boundary=point_initial_gate with the same POINT_INITIAL_GATE_OBSERVATION_TIMEOUT; worker-01 was stopped before leasing. No ATTEMPT_STARTED exists and all four points remain UNRUN.
  - The action-status QoS now matches the authoritative publisher, so at least one other conjunction input remained absent. The current timeout does not record whether the missing class was joints, one or more status topics, the planning-scene future, or graph stability.
  - During recovery replacement startup, one ros2_control_node aborted after a controller-manager service tried to respond to a vanished client (`failed to send response: cannot publish data`). The coordinator ended SUPERVISOR_SHUTDOWN with both results conservative and qualification false.
  - Aggregate cleanup correctly remained false and the exact Broker container survived. External cleanup verified cidfile, batch/generation labels, immutable image, and batch-specific mounts before stopping only that container. Independent audit2 then found empty ownership manifests, no matching process/container/GPU task, and no domain 181-183 owner. MUJOCO_LOG-EXP033.txt was retained.
inferred:
  - F38 closes a real QoS mismatch but cannot be claimed sufficient. The remaining opaque initial-gate timeout must be made class-specific before another semantic fix is considered.
  - The recovery abort is downstream of the already-invalid initial gate and is not a physical point outcome; it remains relevant to abnormal cleanup but does not identify the missing initial observation.
conclusion: INVALID; zero countable attempts. Apply diagnostic-only F39 with RED/GREEN and the ordinary gate, rebuild provenance/image and smoke, then repeat the unchanged execute under EXP-034 to identify the exact absent class.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-oI97UFfw.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-VEilHhNY.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-6mRrcnHi.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p47
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f38.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f38.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f38-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-033.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-033.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-033.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f38/coordinator/events/segment-00000000000000000001.journal
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f38/coordinator/aggregate_results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f38/workers/worker-01/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f38/workers/worker-02/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-033-cleanup-audit2.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP033.txt
hashes:
  live_command_log_sha256: 8ad84d7b1d7a2e968cd66b03d7d232eeb28f9d1459923dcb2877ac90009819c3
  journal_sha256: 519923367c25cb3d80499a02de7c0b28e891823a6fcf9bb480e353dbde66e5f0
  coordinator_aggregate_sha256: fa19edb720ef04138a8be3e2fac16066d27c74cc2333f7a6b4454b994e62f4e8
  worker_01_result_sha256: be7278bf3c0df75b24dbaf98581c69670cac2b89297d629c68ec6e44597c1945
  worker_02_result_sha256: a4b821144eb6814b8befc2521a87a3adb80967b8fff06f02b31d25d0d1ec6e03
  cleanup_audit_sha256: 3ade97d368608fc69fb42d4183be1c88b38cb02765ba9c97b7e7ee67491889d4
  mujoco_warning_log_sha256: 835412001348b8ca2d4d76e069f06c1818425af657cfc77f922b2c6ec73e381b
retained: complete live-small-f38 tree, command/preflight/cleanup reports, journal/projections, Worker diagnostics, ROS logs, container cidfile, MuJoCo log, and all F38 test/build/image/smoke evidence
archived: none
deletion_candidates: p47 and direct-pytest scratch are candidates after readback; nothing was deleted
decision: REPEAT after F39 diagnostic RED/GREEN, ordinary package gate, installed provenance, image rebuild, and dual-model smoke
next_experiment: EXP-034 is reserved for the F39 diagnostic execute repeat; controlled plan-only fault advances to EXP-035 and remains blocked until execute acceptance
```

## EXP-034 — Task 14 class-diagnostic two-Worker execute

```yaml
experiment_id: EXP-034
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T18:13:00+08:00
  - status: RUNNING
    at: 2026-09-12T18:13:00+08:00
  - status: INVALID
    at: 2026-09-12T18:15:20+08:00
prior_experiment: EXP-033
hypothesis: F39 will identify every missing point-initial observation class without changing whether the gate passes; if no class is missing, the unchanged four-point execute proceeds normally.
prediction: Either the normal four-point success contract passes, or each pre-authorization failure names only fixed missing classes and remains INVALID with zero countable attempts.
single_variable: F39 changes only bounded timeout diagnostic text. Selection, configuration, models, N=2, K=2, timeout, gate conjunction, and physical criteria remain frozen; source/install/image and batch/root identities advance because code changed and prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f39
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f39
preconditions:
  - F39 diagnostic RED/GREEN passed 154 adjacent tests and p48 complete ordinary demo gate passed 2767 tests with no error/failure/skip and no benchmark collection.
  - Installed source/build module trees both hash SHA256 839b762488969c3e0a79ae551953be79cdb68d9c07f2290c592348cb018e5b85.
  - Immutable image sha256:35da277058a9dba01ef0ad7073c227d31597c38b3fa0cad2a61e47b500b23f64 binds equal source/verified SHA256 2a99e1fc82cca5f8818f7731db507683f403a4e2ddfe4b6303b7a8ab1078e5d4 and passed fresh dual-model smoke.
  - Fresh inventory and production probe found no related stack process, container, GPU task, or domain 181-183 owner; live-small-f39 is absent.
success_criteria:
  - Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete physical evidence, and clean shutdown.
diagnostic_criteria:
  - Any pre-ATTEMPT_STARTED timeout records only the exact absent class set; it remains INVALID and authorizes no physical conclusion.
provenance:
  executable_source_commit: 9998277763bfe78b77d3fa798909111ad576f135
  executable_source_tree: 2a99e1fc82cca5f8818f7731db507683f403a4e2ddfe4b6303b7a8ab1078e5d4
  runtime_head: clean ledger-only pre-run commit containing this record
  image_id: sha256:35da277058a9dba01ef0ad7073c227d31597c38b3fa0cad2a61e47b500b23f64
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point if authorization is reached; no Gazebo client/window is part of this headless backend.
commands:
  - command: fresh inventory and domain/resource probe to reports/*before-034.json
    exit_code: 0
  - command: unchanged four-point execute to reports/live-small-command-034.*
    exit_code: 1
observed:
  - Both Workers independently leased and reset their first distinct point, then emitted the identical bounded missing set: joint_state, execute_trajectory_status, arm_controller_status, and gripper_controller_status. Planning-scene response and stable graph were present.
  - No ATTEMPT_STARTED exists; all points remain UNRUN and zero outcomes are countable. The coordinator ended CAPACITY_EXHAUSTED after conservative quarantine.
  - Reset transaction source proves it already requires a fresh post-reset converged six-joint sample before re-pausing, but discards the values in ResetReceipt. The point gate then creates a new volatile joint subscriber while paused, so no new controller-manager cycle can publish. Likewise, an action server with no goal has no status event to retain, so even matching transient-local QoS cannot create a sample.
  - Aggregate cleanup correctly remained false and the exact Broker survived. External cleanup verified cidfile, labels, image, and batch mounts before stopping only that container; audit2 found no task process/container/GPU/domain residue. MUJOCO_LOG-EXP034.txt was retained.
inferred:
  - The two missing classes are unobservable under the required paused/pre-goal boundary, not slow. Equivalent positive evidence must cross the reset boundary for joints and use completed all-goal cancel responses for active-goal absence.
conclusion: INVALID; zero countable attempts. Apply F40 with direct RED/GREEN, fresh gates, provenance/image/smoke, then repeat the unchanged execute under EXP-035.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-OgDzg6sz.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-gOX2JA6z.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p48
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f39.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f39.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f39-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-034.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-034.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-034.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f39/coordinator/events/segment-00000000000000000001.journal
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f39/coordinator/aggregate_results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f39/workers/worker-01/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f39/workers/worker-02/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-034-cleanup-audit2.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP034.txt
hashes:
  live_command_log_sha256: 33f280d4694ccd0727b2445a91a36c898534a4967c5e7670ac93160caba184f5
  journal_sha256: 32cf5580d6f0050be9bb99cbd145b6f35436584e7a51064c0ef3e674508fb573
  coordinator_aggregate_sha256: 18de541711fcc4f32f38015bf420780e3356535d9791b843e7daa7822cab6b3f
  worker_01_result_sha256: bcbdacf0f1b5c9cb78ce5f2260c7e54e69c19cff191bc7f4d26c76f2987a29bc
  worker_02_result_sha256: a3d73f4b9e7542c1fc9c4d692bb2dfc4cd3505e707d9245d35e4c356887e350e
  cleanup_audit_sha256: 86d5f8a4aac4bd17651678f0acc5ff3a452adbcfcc683f9b9893db231464d152
  mujoco_warning_log_sha256: f445cda3a88661b3525951a6943537d834d2962541ccdd5eb37b803252a91a23
retained: complete live-small-f39 tree, command/preflight/cleanup reports, journal/projections, Worker diagnostics, ROS logs, container cidfile, MuJoCo log, and all F39 test/build/image/smoke evidence
archived: none
deletion_candidates: p48 and direct-pytest scratch are candidates after readback; nothing was deleted
decision: REPEAT after F40 RED/GREEN, package gates, installed provenance, image rebuild, and dual-model smoke
next_experiment: EXP-035 is reserved for the F40-corrected execute repeat; controlled plan-only fault advances to EXP-036
```

```yaml
checkpoint_id: CP-020
last_valid_experiment: EXP-022
current_hypothesis: F40 makes the point-initial boundary observable without weakening its authorization conjunction, so the unchanged four-point execute can enter countable attempts.
working_tree_status: clean at source commit 8b2ae006aee61ef9602d92a66c08e103f56bfe86 before this ledger-only pre-run commit
owned_processes: NONE
preserved_processes: NONE; the F40 smoke container exited and fresh process, container, GPU, and domain probes found no related owner.
confirmed_conclusions:
  - F40 direct RED pytest-kzXoPL06 failed because the old reset boundary could not carry six joint values; focused GREEN pytest-wX9aUmmy passed after adding the bound field.
  - Adjacent pytest-HlkAsQmG exposed an injected legacy reset stub without joint evidence; the final implementation preserves missing evidence as missing, and the production initial gate fails closed on it instead of fabricating canonical values.
  - Final focused pytest-ul6mlZNW passed 17 tests and adjacent pytest-8svtg05h passed 181 tests. The environment-only pytest-6IazLzg8 collection failure is retained; explicitly sourcing the worktree message package produced passing pytest-bHW8brCZ with 175 tests.
  - Fresh p49 build passed in 1.54 seconds. The complete ordinary so101_demo_py gate passed 2768 tests with zero errors, failures, or skips in 83.64 seconds; benchmark_test was not collected.
  - Source and installed module trees both hash 574d0bbb1b6bd5f0a4f94975fdc453ce0daeed404f5366e014c7b10b5cafaec0; the complete package source tree hashes 22f51331ec58d0e811ea1a2637158a08a48f01f60bbb5de9c48a71bcc9d20d3b.
  - Rebuilt image sha256:fc7f3a6cfa6d67c37593ee83d39ac4bb8dd452a92960244950f2059ecab4872a binds the same source tree and passed fresh dual-model CUDA smoke with one QUALIFIED candidate from each model.
  - Fresh EXP-035 preflight found no related process, container, GPU task, or ROS domain 181-183 owner; 24 CPUs, 25.707 GiB MemAvailable, and 14.911 GiB free GPU exceed admission.
disproven_routes:
  - A subscriber created only after the qualified paused reset cannot prove a joint callback or a never-used action status event; EXP-034's identical dual-Worker missing set was structural, not a timeout tuning problem.
open_risks:
  - F40 has not yet crossed the live ATTEMPT_STARTED boundary.
  - Execute planning, motion, per-point visual/numeric sealing, cleanup, controlled fault, and 20-point qualification remain unaccepted.
retained: all F40 RED/GREEN and adjacent pytest scratch, p49 build/test scratch, installed provenance, immutable image build, dual-model smoke, and EXP-035 preflight reports
archived: none
deletion_candidates: direct pytest scratch and p49 are recorded candidates after readback; nothing was deleted
decision: RUN EXP-035 with the unchanged four-point execute selection and thresholds
next_command: Execute the clean pre-registered EXP-035 batch using image sha256:fc7f3a6cfa6d67c37593ee83d39ac4bb8dd452a92960244950f2059ecab4872a.
```

## EXP-035 — Task 14 reset-boundary two-Worker execute

```yaml
experiment_id: EXP-035
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T18:31:13+08:00
  - status: RUNNING
    at: 2026-09-12T18:31:13+08:00
  - status: INVALID
    at: 2026-09-12T18:36:37+08:00
prior_experiment: EXP-034
hypothesis: F40's reset-bound joint evidence and completed all-goal queries allow both Workers to satisfy the unchanged strict point-initial gate and execute the four selected points.
prediction: Four unique points pass physically with qualification_passed=true and clean shutdown; otherwise any failure remains bounded, attributable, and cannot qualify the batch.
single_variable: F40 replaces only the two observation sources proved impossible by EXP-034. Selection, configuration, models, N=2, K=2, timeout, remaining gate conjunction, and physical criteria are frozen; source/install/image and batch/root identities advance because code changed and prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f40
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f40
preconditions:
  - F40 direct and adjacent gates passed, including 181 final adjacent tests; p49 complete ordinary demo gate passed 2768 tests with no error/failure/skip and no benchmark collection.
  - Installed and source module trees both hash SHA256 574d0bbb1b6bd5f0a4f94975fdc453ce0daeed404f5366e014c7b10b5cafaec0.
  - Immutable image sha256:fc7f3a6cfa6d67c37593ee83d39ac4bb8dd452a92960244950f2059ecab4872a binds equal source/verified SHA256 22f51331ec58d0e811ea1a2637158a08a48f01f60bbb5de9c48a71bcc9d20d3b and passed fresh dual-model smoke.
  - Fresh inventory and production probe found no related stack process, container, GPU task, or domain 181-183 owner; live-small-f40 is absent.
success_criteria:
  - Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete physical/visual/numeric evidence, and clean shutdown.
failure_criteria:
  - Any gate, planning, execution, evidence, isolation, or cleanup failure is attributed exactly and cannot produce qualification_passed=true.
provenance:
  executable_source_commit: 8b2ae006aee61ef9602d92a66c08e103f56bfe86
  executable_source_tree: 22f51331ec58d0e811ea1a2637158a08a48f01f60bbb5de9c48a71bcc9d20d3b
  runtime_head: clean ledger-only pre-run commit containing this record
  image_id: sha256:fc7f3a6cfa6d67c37593ee83d39ac4bb8dd452a92960244950f2059ecab4872a
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per authorized point; no Gazebo client/window is part of this headless backend.
evidence_planned:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-035.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-035.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-035.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f40
commands:
  - command: fresh inventory and production domain/resource probe to reports/*before-035.json
    exit_code: 0
  - command: four-point execute with individually sourced package overlays
    exit_code: 1
  - command: exact Broker identity/mount verification, stop, and cleanup audit2
    exit_code: 0
observed:
  - Both Workers failed in reset_point with ResetFailed initial evidence unavailable before ATTEMPT_STARTED; all points remain UNRUN and zero outcomes are countable.
  - The launch log proves both stacks failed to discover mujoco_ros2_control_plugins/CameraPlugin because the command sourced selected package scripts but omitted the worktree's mujoco_ros2_control_plugins overlay. Plugin-loader construction then failed before SimulationEvidencePlugin could publish the atomic topic.
  - This differs from EXP-034, where the same runtime image and launch configuration loaded the plugin stack and reset completed. It is a command-environment transcription defect, not evidence about F40.
  - Aggregate qualification and cleanup remained false. The exact Broker survived; external cleanup verified its cidfile, immutable image, batch/generation labels, and all four expected mounts before stopping only that container. Audit2 found no related process, container, GPU task, or domain residue.
conclusion: INVALID; zero countable attempts. Source the complete fresh worktree install/setup.zsh, verify both plugin package prefixes resolve inside the worktree, and repeat unchanged under EXP-036.
hashes:
  live_command_log_sha256: 176387970683b83960dbc024ad2da4111e07be3a310c23aec45dd055c9798b94
  journal_sha256: 0e45a87758d51705dae55f8e513a292df926b0d9ba7a2b22c43de44b3d4766f1
  coordinator_aggregate_sha256: 24ae24e366daf6bc4bbe95e9d16227ea634be768af2b2bfae1fa89c34d0ea562
  worker_01_result_sha256: a15236d984443d75394f2b635dce7d1d5c46c3f21addcb0aa218c11f6cb45adc
  worker_02_result_sha256: 4d84a42a731a49daa1261b7151bfbab27b64515b4d7899d7292091622521e153
  cleanup_audit_sha256: ae01a8feb503285958b2639e8d970a60df95380b2c8dd87cbbca9dd6d6e51d4b
retained: F40 test/build/provenance/image/smoke/preflight evidence, complete live-small-f40 tree, command log, Worker results, journal/projections, and cleanup audit
archived: none
deletion_candidates: p49 and direct pytest scratch after readback; nothing will be deleted without user authorization
decision: REPEAT under EXP-036 with the complete worktree overlay source; controlled plan-only fault advances to EXP-037 and remains blocked until execute acceptance
next_experiment: EXP-036 is reserved for the corrected-environment F40 execute repeat
```

## EXP-036 — Task 14 corrected-overlay reset-boundary two-Worker execute

```yaml
experiment_id: EXP-036
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T18:37:41+08:00
  - status: RUNNING
    at: 2026-09-12T18:37:41+08:00
  - status: INVALID
    at: 2026-09-12T18:41:24+08:00
prior_experiment: EXP-035
hypothesis: With the complete fresh worktree overlay sourced, F40's reset-bound joint evidence and completed all-goal queries allow both Workers to satisfy the strict point-initial gate and execute the unchanged four points.
prediction: Both plugin classes load, four unique points pass physically with qualification_passed=true and clean shutdown; otherwise any failure remains bounded, attributable, and cannot qualify the batch.
single_variable: Only command environment sourcing changes from selected package scripts to the complete worktree install/setup.zsh. F40 source, image, selection, configuration, models, N=2, K=2, timeout, gates, and physical criteria remain frozen; batch/root identities advance because prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f40b
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f40b
preconditions:
  - EXP-035 exact Broker cleanup and audit2 found zero related process, container, GPU task, or domain residue.
  - Fresh resource/inventory preflight again found 24 CPUs, 25.765 GiB MemAvailable, 14.914 GiB free GPU, and no related process/container/GPU/domain owner.
  - Overlay readback resolves mujoco_ros2_control, mujoco_ros2_control_plugins, mujoco_ros2_control_msgs, so101_mujoco_support, so101_teleop, and so101_demo_py exclusively from this worktree before /opt/ros/jazzy.
  - p49, installed provenance, immutable image sha256:fc7f3a6cfa6d67c37593ee83d39ac4bb8dd452a92960244950f2059ecab4872a, and dual-model smoke remain unchanged and valid.
success_criteria:
  - Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete physical/visual/numeric evidence, and clean shutdown.
failure_criteria:
  - Any gate, planning, execution, evidence, isolation, or cleanup failure is attributed exactly and cannot produce qualification_passed=true.
provenance:
  executable_source_commit: 8b2ae006aee61ef9602d92a66c08e103f56bfe86
  executable_source_tree: 22f51331ec58d0e811ea1a2637158a08a48f01f60bbb5de9c48a71bcc9d20d3b
  runtime_head: clean ledger-only pre-run commit containing this record
  image_id: sha256:fc7f3a6cfa6d67c37593ee83d39ac4bb8dd452a92960244950f2059ecab4872a
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight_hashes:
  domain_sha256: 9db388e228517e4e21909ecd4f3afa9d2646206a8e1b343d298e9f287d758db9
  inventory_sha256: b10475323b4c5e11eeefa6d787f2aa4bfb7b0a20ef80299357c72c8a36540dcb
  overlay_sha256: 7f3f483a6a616f7b675f3e9e13a91462ebdbba1baa4a65bd800fe25fe3433a17
visual_method: Original-resolution immutable MuJoCo offscreen RGB per authorized point; no Gazebo client/window is part of this headless backend.
evidence_planned:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-036.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-036.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/overlay-preflight-before-036.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-036.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f40b
commands:
  - command: fresh resource/inventory/complete-overlay preflight
    exit_code: 0
  - command: unchanged four-point execute after complete worktree install/setup.zsh
    exit_code: 1
  - command: exact Broker identity/mount verification, stop, and cleanup audit2
    exit_code: 0
observed:
  - Both Workers loaded CameraPlugin and the atomic SimulationEvidence plugin, completed reset, completed every F40 observation future, and then failed with the identical bounded boundary POINT_INITIAL_GATE_OBSERVATION_REJECTED before ATTEMPT_STARTED.
  - All four points remain UNRUN; zero outcomes are countable. The coordinator ended CAPACITY_EXHAUSTED with both failed points INVALID and both Workers quarantined.
  - One ros2_control_node later aborted during conservative recovery when a controller-manager service attempted to respond to a vanished client; the other stack then observed arm_controller absent. These events occurred after the upstream point-gate rejection and do not explain it.
  - The existing aggregate rejection does not identify which unchanged predicate failed. F41 diagnostic-only attribution is required before any semantic fix.
  - Aggregate qualification and cleanup remained false. External cleanup verified the exact surviving Broker cidfile, image, batch/generation labels, and batch-specific mounts before stopping it; audit2 found no related process, container, GPU task, or domain residue.
  - The late-created MUJOCO_LOG.TXT was moved without content change into the registered report root as MUJOCO_LOG-EXP036.txt and retained.
conclusion: INVALID; zero countable attempts. Apply F41 diagnostic-only RED/GREEN and ordinary gates, then repeat unchanged under EXP-037.
hashes:
  live_command_log_sha256: 020866235aea03c7c1d9f49f92e21e78e3704c01e5af820b05e746e9f35a97c2
  journal_sha256: 8c7bbd55d03c5aeb66889d8a089d4c307808cdd0e33115d5570f9e51f0678c81
  coordinator_aggregate_sha256: 9191b460a64628cff584c202799166a3bf55d5614b35a60bc11bbb22e00bd9d2
  worker_01_result_sha256: 59fff5e359262a66bbe0b3d3af8e7c605a796d6ab61f6c7e154bd8a543fb1368
  worker_02_result_sha256: 0e178c5328b319b9083f061b03fbf55d3e3725aee0b47574bf9a4e42722b79e5
  cleanup_audit_sha256: fcef54e0e763add5cc8079bbb7e8653bd69628b78cc3fa3dc07802cc8561891b
  mujoco_log_sha256: 5fb81c84f2c34691a31e4ce959768dc7c31a063925d29929e451657d892cb614
retained: complete live-small-f40b tree, command/preflight/cleanup reports, journal/projections, Worker diagnostics, ROS logs, container cidfile, and all unchanged F40 qualification evidence
archived: none
deletion_candidates: p49 and direct pytest scratch are candidates after readback; nothing was deleted
decision: REPEAT after F41 diagnostic RED/GREEN, package gate, installed provenance, image rebuild, and dual-model smoke
next_experiment: EXP-037 is reserved for the F41 diagnostic execute repeat; controlled plan-only fault advances to EXP-038 and remains blocked until execute acceptance
```

```yaml
checkpoint_id: CP-021
last_valid_experiment: EXP-022
current_hypothesis: F41 will identify the exact remaining point-initial predicate without changing authorization behavior.
working_tree_status: clean at source commit 6ead76c3dc9b7eb27cce626624ffdc2700ada601 before this ledger-only pre-run commit
owned_processes: NONE
preserved_processes: NONE; EXP-036 exact cleanup and fresh EXP-037 preflight found no related process, container, GPU task, or domain owner.
confirmed_conclusions:
  - F41 formal RED pytest-ZEZVbDai failed on the prior opaque rejection; focused GREEN pytest-ZPukPIk6 passed and adjacent pytest-OKdRpt0g passed 155 tests.
  - The diagnostic enumerates type, reset identity, freshness, joints, goals, attachment, contact, graph stability, and exact Worker nodes in fixed order while leaving every predicate and success receipt unchanged.
  - Fresh p50 build passed in 1.52 seconds; the complete ordinary so101_demo_py gate passed 2769 tests with zero errors, failures, or skips in 83.92 seconds and did not collect benchmark_test.
  - Source and installed module trees both hash fb946a5fafa5b508d964bb036224d3fb59326cc5096a92d615bc1165627674ab; complete package source hashes 44315a1995588cc424db966f7f79cce39ab6e043a9efa3bc058006417ee79996.
  - Rebuilt image sha256:9858a5ab5a67f44b5979707c3c2eb0f5183c20e392c6b5f6b80f9b3827fd4777 binds the same source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate from each model.
  - A malformed shell command created only empty task14-f41-smoke/workers directories before parse failure; no container or report was created. The empty root is retained and not reused; valid smoke evidence is task14-f41-smoke2.
  - Fresh EXP-037 preflight found no related process/container/GPU/domain owner, 24 CPUs, 25.661 GiB MemAvailable, 14.914 GiB free GPU, the complete worktree overlay, and the exact F41 image ID.
open_risks:
  - The exact failing predicate in EXP-036 is unknown until EXP-037 runs.
  - No ATTEMPT_STARTED, planning, motion, point evidence, fault, or 20-point qualification has yet been accepted.
retained: F41 RED/GREEN/adjacent scratch, p50, installed provenance, image build, empty failed smoke root, valid smoke2 root, and EXP-037 preflight reports
archived: none
deletion_candidates: direct pytest scratch and p50 after readback; nothing was deleted
decision: RUN EXP-037 with unchanged F41 source, four-point selection, and complete overlay
next_command: Execute the clean pre-registered diagnostic batch using image sha256:9858a5ab5a67f44b5979707c3c2eb0f5183c20e392c6b5f6b80f9b3827fd4777.
```

## EXP-037 — Task 14 predicate-diagnostic two-Worker execute

```yaml
experiment_id: EXP-037
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T18:48:26+08:00
  - status: RUNNING
    at: 2026-09-12T18:48:26+08:00
  - status: INVALID
    at: 2026-09-12T18:54:28+08:00
prior_experiment: EXP-036
hypothesis: F41 identifies the exact unchanged point-initial predicate rejected on both Workers; if none is rejected, the four-point execute proceeds normally.
prediction: Either four unique points pass physically with qualification_passed=true, or each pre-authorization failure names only fixed rejected predicates and remains INVALID with zero countable attempts.
single_variable: F41 changes only bounded rejection diagnostic text. F40 semantics, complete overlay, selection, configuration, models, N=2, K=2, timeout, gate conjunction, and physical criteria remain frozen; source/install/image and batch/root identities advance because code changed and prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f41
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f41
preconditions:
  - F41 RED/GREEN and adjacent gates passed; p50 complete ordinary demo gate passed 2769 tests with no error/failure/skip and no benchmark collection.
  - Installed/source module trees both hash SHA256 fb946a5fafa5b508d964bb036224d3fb59326cc5096a92d615bc1165627674ab.
  - Immutable image sha256:9858a5ab5a67f44b5979707c3c2eb0f5183c20e392c6b5f6b80f9b3827fd4777 binds equal source/verified SHA256 44315a1995588cc424db966f7f79cce39ab6e043a9efa3bc058006417ee79996 and passed fresh dual-model smoke.
  - Fresh inventory/resource/overlay probe found no related process, container, GPU task, or domain 181-183 owner and resolves all runtime packages inside the worktree.
success_criteria:
  - Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete physical/visual/numeric evidence, and clean shutdown.
diagnostic_criteria:
  - Any pre-ATTEMPT_STARTED rejection records only the fixed rejected predicate names; it remains INVALID and authorizes no physical conclusion.
provenance:
  executable_source_commit: 6ead76c3dc9b7eb27cce626624ffdc2700ada601
  executable_source_tree: 44315a1995588cc424db966f7f79cce39ab6e043a9efa3bc058006417ee79996
  runtime_head: clean ledger-only pre-run commit containing this record
  image_id: sha256:9858a5ab5a67f44b5979707c3c2eb0f5183c20e392c6b5f6b80f9b3827fd4777
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per authorized point if reached; no Gazebo client/window is part of this headless backend.
evidence_planned:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-037.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-037.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/overlay-preflight-before-037.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-037.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f41
result: >-
  Command exit was 1 after 79.28 s. Worker-02 reached the task_start point-initial boundary and
  F41 reported exactly POINT_INITIAL_GATE_OBSERVATION_REJECTED:contact,worker_nodes. Worker-01
  stopped WORKER_NOT_READY after the peer failure/recovery path. No ATTEMPT_STARTED event exists;
  all four points remain UNRUN, so zero attempts are countable and no physical conclusion is
  authorized. The contact predicate incorrectly consumed the broad evidence.has_contact flag,
  which includes the required table support contact, instead of only left/right fingertip contact.
  The exact Worker node inventory omitted the three active controller nodes arm_controller,
  gripper_controller, and joint_state_broadcaster that the same gate requires. These are bounded
  point-initial observation defects, not a planning or physical failure.
cleanup: >-
  The only surviving owned Broker was container
  02d30567605b10d4e58f2a97beea3fb39155078b66ccf19a3bf6b9d9633472. Before stopping it, exact
  readback verified image sha256:9858a5ab5a67f44b5979707c3c2eb0f5183c20e392c6b5f6b80f9b3827fd4777,
  batch label parallel-small-20260912-v1-f41, generation 1, and only the registered broker input,
  runtime, and model mounts. It was stopped by exact CID. Post-stop process/container/GPU audit
  found zero related residue. The late MuJoCo log was moved without deletion into the registered
  reports root.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 915c541ac85d80f76346903c1807793c803f2dd5bd1570bc8f32b844d189f30e
command_time_sha256: e9e8b601e5bdcb888de02f22638c7b58096c4c2b36ac007e86f0ad01c334593d
aggregate_sha256: 556aaafed719472b8be5f06faf8bc804e4a4a080933a3f579f3e46488eace72d
coordinator_aggregate_sha256: 4d7f1dff2510db2d4d194695f888de94d5cc301c8bd29786669cb694c007adf5
worker_01_result_sha256: be7278bf3c0df75b24dbaf98581c69670cac2b89297d629c68ec6e44597c1945
worker_02_result_sha256: 50f1c428735e7e6c84f9d7384e946c3ee997cf565ede7f0be39826e00b6cddd9
mujoco_log_sha256: 5ef2af162c7beb4479ea04aa63773666507b53f6ec6e9cfd1e73068841485066
conclusion: INVALID; zero countable attempts. Apply F42 with direct RED/GREEN, fresh gates, provenance/image/smoke, then repeat the unchanged execute under EXP-038.
retained: all prior evidence plus complete EXP-037 batch and report artifacts
archived: none
deletion_candidates: p50 and direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-022
last_valid_experiment: EXP-022
current_hypothesis: F42 corrects only the two false initial-gate rejections identified by EXP-037, allowing the unchanged four-point execute to reach authorization without admitting fingertip contact or an unknown Worker node.
working_tree_status: clean at executable source commit df0e543dc32e63284084dd815bfb183551c277c0 before this ledger-only pre-run commit
owned_processes: NONE
preserved_processes: NONE; EXP-037 exact cleanup and fresh EXP-038 preflight found no related process, container, GPU task, or domain 181-183 owner.
confirmed_conclusions:
  - F42 formal RED pytest-G1MY33fi failed independently on table-only contact mapping and the omitted legal controller nodes. Focused GREEN pytest-lDzeNeaD passed 2 tests, the complete runtime file pytest-Dn96hJCB passed 15 tests, and adjacent pytest-iOajWrPg passed 155 tests.
  - The earlier pytest-FuqiG7Co is retained but invalid as semantic evidence because the incomplete package overlay selected the underlay message package during import.
  - F42 maps only nonempty left/right fingertip contact collections to the forbidden-contact bit. The broad atomic has_contact flag and other_object_contacts, including the required table support, are not authorization failures. Direct coverage still rejects a nonempty fingertip collection.
  - The exact Worker inventory now includes arm_controller, gripper_controller, and joint_state_broadcaster, while direct coverage still rejects every missing or unknown node.
  - p51 is retained as an invalid build-environment run: omission of --symlink-install caused one source-layout contract failure after 2768 passes. Fresh p52 used the required symlink install, built in 1.39 seconds, passed all 2769 ordinary tests in 83.77 seconds wall with zero errors, failures, or skips, and did not collect benchmark_test. Package-scoped colcon readback reports 2769 tests, zero errors/failures/skips.
  - Source and installed module trees both hash 33bea12d30ad2121e9b7a34c79b0c69413b907eab379cd155ee89010a1bf1acd; complete package source hash is e233b76a84f43e62ad8e73ef5be7a455eec8fd88cf71906689081888ef61b6b7.
  - Rebuilt image sha256:cecab6876dfb118890b3a290418433c631f67f97d143f3a3423aca2e07b44de3 binds the same complete source and passed fresh CUDA smoke: YOLO first and Grounded-SAM each returned exactly one QUALIFIED candidate from the exact reviewed RGB image.
  - Fresh EXP-038 preflight found 24 CPUs, 25.604 GiB MemAvailable, 15269 MiB free GPU memory, no related process/container/GPU/domain owner, all three runtime package prefixes inside this worktree, and exact immutable-image labels.
open_risks:
  - EXP-038 must prove the live graph equals the corrected exact inventory and that no later pre-authorization or physical gate fails.
  - No ATTEMPT_STARTED, planning, motion, point evidence, controlled fault, or 20-point qualification has yet been accepted.
retained: all F42 RED/GREEN/adjacent scratch, invalid p51, valid p52, installed provenance, immutable image build, dual-model smoke, EXP-037 evidence, and EXP-038 preflight reports
archived: none
deletion_candidates: direct pytest scratch plus p50, p51, and p52 after readback; nothing was deleted
decision: RUN EXP-038 with unchanged four-point selection, physical thresholds, and complete worktree overlay
next_command: Execute the clean pre-registered F42 batch using image sha256:cecab6876dfb118890b3a290418433c631f67f97d143f3a3423aca2e07b44de3.
```

## EXP-038 — Task 14 corrected-contact-and-node two-Worker execute

```yaml
experiment_id: EXP-038
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T19:05:05+08:00
  - status: RUNNING
    at: 2026-09-12T19:05:05+08:00
  - status: INVALID
    at: 2026-09-12T19:07:33+08:00
prior_experiment: EXP-037
hypothesis: F42 removes exactly the two false point-initial rejections while retaining strict fingertip-contact and exact-node rejection, so both Workers can execute four unique points and satisfy every physical criterion.
prediction: Four unique points finish PASSED with qualification_passed=true, each Worker processes at most two points, and no lease, process, domain, session, controller, socket, or evidence identity overlaps.
single_variable: F42 changes only forbidden-contact projection from broad object contact to fingertip contact and adds the three required controller nodes to the exact inventory. F40/F41 semantics, complete overlay, selection, configuration, models, N=2, K=2, timeouts, other gate predicates, and physical criteria remain frozen; source/install/image and immutable batch identities advance.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f42
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f42
preconditions:
  - F42 RED/GREEN and adjacent gates passed; p52 complete ordinary demo gate passed 2769 tests with no error/failure/skip and no benchmark collection.
  - Installed/source module trees both hash SHA256 33bea12d30ad2121e9b7a34c79b0c69413b907eab379cd155ee89010a1bf1acd.
  - Immutable image sha256:cecab6876dfb118890b3a290418433c631f67f97d143f3a3423aca2e07b44de3 binds equal source/verified SHA256 e233b76a84f43e62ad8e73ef5be7a455eec8fd88cf71906689081888ef61b6b7 and passed fresh dual-model smoke.
  - Fresh inventory/resource/overlay probe found no related process, container, GPU task, or domain 181-183 owner and resolves all runtime packages inside the worktree.
success_criteria:
  - Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete physical/visual/numeric evidence, and clean shutdown.
failure_criteria:
  - Any physical, planning, recovery, cleanup, ownership, provenance, or invariant failure remains exactly classified and cannot contribute a pass.
provenance:
  executable_source_commit: df0e543dc32e63284084dd815bfb183551c277c0
  executable_source_tree: e233b76a84f43e62ad8e73ef5be7a455eec8fd88cf71906689081888ef61b6b7
  runtime_head: clean ledger-only pre-run commit containing this record
  image_id: sha256:cecab6876dfb118890b3a290418433c631f67f97d143f3a3423aca2e07b44de3
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per authorized point; every produced point image must be visually inspected after the batch.
evidence_planned:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-038.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-038.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/overlay-preflight-before-038.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-038.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f42
result: >-
  Command exit was 1 after 40.43 s. Worker-01 rejected task_start and Worker-02 rejected
  cup_test_forward_5cm at the point-initial boundary with exactly
  POINT_INITIAL_GATE_OBSERVATION_REJECTED:worker_nodes. The F42 contact correction therefore
  removed the independent false contact rejection on both Workers, while exact node equality
  remained fail closed. No ATTEMPT_STARTED event exists; all four points remain UNRUN and zero
  attempts are countable. The current bounded diagnostic does not reveal the actual stable graph,
  so changing the whitelist again without evidence is not authorized.
cleanup: >-
  The only surviving owned Broker was exact CID
  5f41ae9c88d7443934b7b5065358612dbf278f5fcffd6d6e3c3c71ad0c6f54d9. Readback before stop
  verified the exact F42 image, batch/generation labels, and only registered runtime/input/model
  mounts. It was stopped by exact CID. Post-stop process/container/GPU audit found zero related
  residue. The late MuJoCo log was moved without deletion into the registered reports root.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 9d1696a47289316b40de14e86febb00af8ea20a3a4cbe2d0aa1cfdb2fb7a3fd9
command_time_sha256: 6439551d29fcee35a2775b02d02e7f9e2ae9b78cdb2b92aeb89ecd1561e67075
aggregate_sha256: 556aaafed719472b8be5f06faf8bc804e4a4a080933a3f579f3e46488eace72d
coordinator_aggregate_sha256: 8fb5bfeebc6bcbd3d7a3f168b6078cf16b3185f07ac7c50e72ecf5adcaf184ba
worker_01_result_sha256: 2a0b672f70f3d948cb6d74c15d8a1dc67d2451e0d6653ee518cb57f93bcc3bb1
worker_02_result_sha256: be96056078ea1a8df468000f6b7f790232ef7ae6a42c712cf2605a7098d676b6
mujoco_log_sha256: 69fbe8c9c3244500131016943cf43c33346fd09a98806eb655d521a14906dc59
conclusion: INVALID; zero countable attempts. Add F43 diagnostic-only bounded expected/observed node attribution, rebuild, and repeat under EXP-039 before any whitelist change.
retained: all prior evidence plus complete EXP-038 batch and report artifacts
archived: none
deletion_candidates: p51, p52, and direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-023
last_valid_experiment: EXP-022
current_hypothesis: F43 will expose the exact stable graph difference on both Workers without changing node equality or any authorization predicate.
working_tree_status: clean at diagnostic source commit f397cd401d66f3324b7f6bbf19c33f77b48a8f58 before this ledger-only pre-run commit
owned_processes: NONE
preserved_processes: NONE; EXP-038 exact cleanup and fresh EXP-039 preflight found no related process, container, GPU task, or domain owner.
confirmed_conclusions:
  - F43 formal RED pytest-cURIroAy failed on absent node detail; focused GREEN pytest-Pd6981M6 passed and adjacent pytest-EnGgcPzy passed 156 tests.
  - Node diagnostics are deterministic JSON with sorted expected/missing/unexpected/duplicate arrays, at most 16 entries per array and 96 characters per entry. Exact tuple equality and all other predicates are unchanged.
  - Fresh p53 symlink build passed in 1.51 seconds; all 2770 ordinary tests passed in 83.67 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source and installed module trees both hash c6973196f107b2e34a17d6f27bf41de924994cb4fa3968def2aaee23a0067564; complete package source hash is 2c4cb5515c3d07ea688b4eb1effe36008d88081006258f1f8b46c2817ad2394c.
  - Rebuilt image sha256:9e48dfee5c05a1f7c3137b712b631cc740dbe981a54a734c7294adfb132322ca binds the same complete source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate per model.
  - Fresh EXP-039 preflight found 24 CPUs, 25.517 GiB MemAvailable, 15272 MiB free GPU memory, and no related process/container/GPU/domain owner.
open_risks:
  - The exact missing/unexpected/duplicate node set is unknown until EXP-039 runs.
  - No physical attempt or point has yet been authorized.
retained: F43 RED/GREEN/adjacent scratch, p53, installed provenance, image build, smoke, EXP-038 evidence, and EXP-039 preflight reports
archived: none
deletion_candidates: direct pytest scratch plus p51-p53 after readback; nothing was deleted
decision: RUN EXP-039 with unchanged source semantics, selection, and physical thresholds
```

## EXP-039 — Task 14 bounded-node-diagnostic two-Worker execute

```yaml
experiment_id: EXP-039
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T19:13:13+08:00
  - status: RUNNING
    at: 2026-09-12T19:13:13+08:00
  - status: INVALID
    at: 2026-09-12T19:15:52+08:00
prior_experiment: EXP-038
hypothesis: F43 identifies the complete stable Worker graph difference while preserving the F42 authorization semantics.
prediction: Either the four points execute and pass, or every node rejection contains bounded deterministic missing/unexpected/duplicate detail with zero countable attempts.
single_variable: Diagnostic payload only. F42 semantics, complete overlay, selection, configuration, models, N=2, K=2, timeouts, gate conjunction, and physical criteria remain frozen; source/install/image and immutable batch identities advance.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f43
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f43
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
diagnostic_criteria: A pre-ATTEMPT_STARTED worker_nodes rejection reports bounded exact differences, remains INVALID, and authorizes no physical conclusion.
provenance:
  executable_source_commit: f397cd401d66f3324b7f6bbf19c33f77b48a8f58
  executable_source_tree: 2c4cb5515c3d07ea688b4eb1effe36008d88081006258f1f8b46c2817ad2394c
  runtime_head: clean ledger-only pre-run commit containing this record
  image_id: sha256:9e48dfee5c05a1f7c3137b712b631cc740dbe981a54a734c7294adfb132322ca
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per authorized point if reached.
result: >-
  Command exit was 1. Both Workers rejected only worker_nodes before ATTEMPT_STARTED. The diagnostic
  proves every required node was present (missing=[] and duplicates=[]), while the stable graph also
  contained legitimate in-process ros2_control/MoveIt nodes including /controller_manager,
  /move_group/moveit, runtime-suffixed /move_group_private_*, runtime-suffixed /moveit_*,
  /moveit_simple_controller_manager, /robotsystem, and at least one /transform_li... node. The
  Worker failure-message contract truncated the 513-byte message at 512 bytes, so the final name(s)
  cannot be inferred. All four points remain UNRUN and zero attempts are countable.
cleanup: >-
  Exact CID b81689ea3bb94088d7848a24cabb1b13f795bd2a04e31d8f0bacfaf2ae6a0f47 was verified against the
  F43 immutable image, batch/generation labels, and registered mounts, then stopped. Post-stop
  process/container/GPU audit found zero related residue. The late MuJoCo log was moved without
  deletion to reports/MUJOCO_LOG-EXP039.txt.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: d33815217c3ede1456d41bdd50bcbad3e02ca6c53850e62b908acbe637322dc1
command_time_sha256: 5e0b72eeadb79afafde8eae8b6056e4d62cd2c7982c4ed224dbe2756daa9ccd0
worker_01_result_sha256: 26836d1369090e6fa523a5b2df8609bde8560be075228560233dd61b25c825c4
worker_02_result_sha256: 4e20fe78d4c891ea16058bcaeef071844111a3a55f0567b4d225d9f56543edb3
mujoco_log_sha256: 25d04eff18aa03e7c96a85b407b2ec1a19fddbb0856194a972f09ffdb4bd3054
conclusion: INVALID; zero countable attempts. Compress F43 detail under the existing 512-byte Worker bound, retain exact equality, and repeat diagnostic-only as EXP-040.
retained: all prior evidence plus complete EXP-039 batch and reports
archived: none
deletion_candidates: p53 and direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-024
last_valid_experiment: EXP-022
current_hypothesis: F44 will retain the complete stable graph difference inside the immutable Worker result without changing authorization.
working_tree_status: clean at diagnostic source commit 4b1550d629fb97314e8b336115396493c5658c48 before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F44 RED pytest-h0JdcJN2 failed on redundant/unbounded detail; focused GREEN pytest-d43yREnP passed and adjacent pytest-c6BGQCHc passed 156 tests.
  - The compact payload omits redundant expected values, retains missing/unexpected/duplicates/truncated, is at most 320 bytes, and direct integration proves `_bounded_failure_message` does not truncate it.
  - Fresh p54 symlink build passed in 1.53 seconds; all 2770 ordinary tests passed in 83.65 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source/install module trees both hash fc1420d40bc1651b848c22628c4f01d61425bf16bd56b15a4968526e63e121c6; complete source hash is 2d7f8f2c352ce313c12684c3b7eec6c0c4496ad73353192cc2630076f22a6d8d.
  - Rebuilt image sha256:18db5459d2795f922dd659bd303292e42df7230e682ca1a45fc135abb131d3fb binds that source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate per model.
  - Fresh preflight found 24 CPUs, 25.437 GiB MemAvailable, 15272 MiB free GPU, and no related container, GPU process, or ROS domain owner.
open_risks:
  - Full internal-node inventory remains unknown until EXP-040.
retained: F44 RED/GREEN/adjacent scratch, p54, provenance/image/smoke, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p54 after readback; no deletion authorized
decision: RUN diagnostic-only EXP-040 with unchanged authorization and physical inputs
```

## EXP-040 — Task 14 compact-node-diagnostic two-Worker execute

```yaml
experiment_id: EXP-040
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T19:20:30+08:00
  - status: RUNNING
    at: 2026-09-12T19:20:30+08:00
  - status: INVALID
    at: 2026-09-12T19:25:26+08:00
prior_experiment: EXP-039
hypothesis: F44 preserves the full stable unexpected-node set in each Worker result under the existing 512-byte failure boundary.
prediction: A worker_nodes rejection contains parseable complete missing/unexpected/duplicates/truncated JSON, with zero countable attempts.
single_variable: Compact diagnostic serialization only; F42 authorization semantics and every runtime/physical input remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f44
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f44
provenance:
  executable_source_commit: 4b1550d629fb97314e8b336115396493c5658c48
  executable_source_tree: 2d7f8f2c352ce313c12684c3b7eec6c0c4496ad73353192cc2630076f22a6d8d
  image_id: sha256:18db5459d2795f922dd659bd303292e42df7230e682ca1a45fc135abb131d3fb
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
result: >-
  Command exit was 1. Both Workers produced complete parseable node diagnostics before
  ATTEMPT_STARTED. Every required node was present, no duplicate FQN existed, and the only seven
  additional nodes were /controller_manager, /move_group/moveit, one /move_group_private_<digits>,
  one /moveit_<digits>, /moveit_simple_controller_manager, /robotsystem, and one
  /transform_listener_impl_<lower-hex>. The two Workers had the same seven categories with only the
  three expected runtime-generated suffixes differing. Exact whole-graph tuple equality therefore
  contradicts the design's actual requirement (no old same-Worker node or cross-Worker control
  topic) and is impossible for this legitimate isolated stack. All points remain UNRUN and zero
  attempts are countable.
cleanup: >-
  Exact CID feb2befbe9a4c5761d88321c04568177064b471aacaea8fa460ea60579e06fa1 was verified against the
  F44 immutable image, batch/generation labels, and registered mounts, then stopped. Post-stop
  process/container/GPU audit found zero related residue. The late MuJoCo log was moved without
  deletion to reports/MUJOCO_LOG-EXP040.txt.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 7f6b63ba28544902215de406e298cdf5d49f8b83020b5e943220edc8d3e7f856
command_time_sha256: 6889f299d2529b75204505fca07fa88f0aac4451d44222e1529e0d08d7f8ae7d
worker_01_result_sha256: 91097bf68c47b87f90ea5cdac370623b941f8fc490b1ffe5088920a98051ad87
worker_02_result_sha256: 7f914ad038c749b9eab0305cc7d417c995ee4934077a0ba2d7ebce10e38217dc
mujoco_log_sha256: e3afffd59ffc84f9efa47a1388d31e3931eb6cfa176ec701491d0c581ccc82d2
conclusion: INVALID; zero countable attempts. Replace impossible whole-graph equality with exact required nodes plus an exact one-per-category internal-node topology under F45, retaining unknown/missing/duplicate rejection.
retained: complete immutable EXP-040 batch and reports plus all prior evidence
archived: none
deletion_candidates: p54/direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-025
last_valid_experiment: EXP-022
current_hypothesis: F45 accepts exactly the observed isolated runtime topology while rejecting stale, malformed, duplicate-category, and unknown nodes, allowing the four-point execute to begin.
working_tree_status: clean at executable source commit 8863a47252ac937ce781cb76b5c1902726b6b02c before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F45 formal RED pytest-L7eUOGkm failed on the legitimate observed topology. Focused GREEN pytest-v2vBoRrS passed. The first adjacent run pytest-UOczVf8W exposed one stale test fixture after 155 passes; corrected-fixture pytest-2nZSZlK4 passed all 156 tests.
  - The node gate requires all 8 fixed Worker nodes, all 4 fixed internal nodes, and exactly one member of each of 3 strictly formatted generated-node categories. Direct cases reject missing, unknown, duplicate category/FQN, and malformed suffixes.
  - Fresh p55 symlink build passed in 1.52 seconds; all 2770 ordinary tests passed in 83.77 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source/install module trees both hash 9fce9ffc8914b9f298a59e1aa567bf76e717e0cf9fa5e646102df06598441ca3; complete source hash is ba376796ab59d5dd5cc98865927d0a5682416626a725602c122c721bdd896f6e.
  - Rebuilt image sha256:f5e02ccc4e8869ee81fbc71e84c2fab61d5c5c3fda75309406a7ffd415bbde88 binds that source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate per model.
  - Fresh preflight found 24 CPUs, 25.363 GiB MemAvailable, 15272 MiB free GPU, and no related container, GPU process, or ROS domain owner.
open_risks:
  - EXP-041 is the first run able to reach ATTEMPT_STARTED; downstream perception/planning/execution evidence remains unproven.
retained: F45 RED/GREEN/adjacent scratch, p55, provenance/image/smoke, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p55 after readback; no deletion authorized
decision: RUN EXP-041 with the unchanged four points and physical criteria
```

## EXP-041 — Task 14 stable-topology two-Worker execute

```yaml
experiment_id: EXP-041
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T19:30:23+08:00
  - status: RUNNING
    at: 2026-09-12T19:30:23+08:00
  - status: INVALID
    at: 2026-09-12T19:32:50+08:00
prior_experiment: EXP-040
hypothesis: The evidence-derived exact topology gate removes the impossible full-graph equality while preserving stale-node isolation, allowing two Workers to execute four unique points.
prediction: Four unique points finish PASSED with qualification_passed=true, each Worker handles at most two points, and every isolation/physical/visual/cleanup invariant holds.
single_variable: F45 node-topology semantics only. Contact, reset/session, freshness, joints, goals, attachment, graph stability, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f45
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f45
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 8863a47252ac937ce781cb76b5c1902726b6b02c
  executable_source_tree: ba376796ab59d5dd5cc98865927d0a5682416626a725602c122c721bdd896f6e
  image_id: sha256:f5e02ccc4e8869ee81fbc71e84c2fab61d5c5c3fda75309406a7ffd415bbde88
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per authorized point, followed by complete per-image visual inspection.
result: >-
  Command exit was 1 after 17.78 s at ProcessSupervisor.start for the second Worker with
  SupervisorError CHILD_IDENTITY. No Worker stack, point lease, reset, ATTEMPT_STARTED, or physical
  action occurred; worker-01 recorded WORKER_NOT_READY and the owned-process manifest was empty.
  The child was created with start_new_session=True, but start() performs two immediate /proc reads
  without yielding for the child-side setsid transition. The observed intermittent failure after
  many successful launches is the bounded parent/child session-establishment race. The existing
  fail-closed cleanup reaped the exact Popen child and did not signal an unverified process group.
cleanup: >-
  The exact surviving Broker CID 965eef057b75883dd6218a5b12ffb072279a330c397382552cefea0fa355233d
  was verified against the F45 image, batch/generation labels, and registered mounts, then stopped.
  Post-stop audit found zero related process, container, GPU task, or domain owner.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 058e212070e49ee371b383763772ab1840adeca20393cf6cd76c786d3d8f3e80
command_time_sha256: 17ec2dbc491c15e5f618fb2600ab555d13efb8c072ce3b1d393bd721977dda37
owned_processes_sha256: c61fb2bf4c7c09b4c72b24b314a25423547fc4890246770a0933c3600c9f4621
worker_01_result_sha256: be7278bf3c0df75b24dbaf98581c69670cac2b89297d629c68ec6e44597c1945
conclusion: INVALID; zero countable attempts. Add a bounded alive-child retry for the start_new_session /proc identity transition, retaining exact cleanup and PID-reuse rejection, then repeat under EXP-042.
retained: complete EXP-041 batch/reports plus all prior evidence
archived: none
deletion_candidates: p55/direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-026
last_valid_experiment: EXP-022
current_hypothesis: F46 removes only the bounded child-session observation race, allowing the unchanged four-point execute to reach the already-qualified Worker topology gate.
working_tree_status: clean at executable source commit c5cc7fc987d119e4d5c15fd50635f97899448be6 before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F46 formal RED pytest-fDK4r9SW failed when the child became a self-led session on the third identity read. Focused GREEN pytest-MdEc5jYV passed 2 tests and adjacent pytest-ESVDyxI3 passed all 39 process-supervision tests.
  - Process startup now performs at most eight identity reads with 1 ms yields only while the exact Popen child remains alive. It admits only complete pgid==pid identity and never signals a persistent foreign or incomplete group.
  - Fresh p56 symlink build passed in 1.50 seconds. All 2771 ordinary package tests passed in 82.95 seconds wall with zero errors, failures, or skips and no benchmark collection. The first build evidence wrapper is retained as invalid because it used zsh's read-only status variable after a successful build; the corrected r2 wrapper recorded exit 0.
  - Source/install module trees both hash d6bc05d7f22d8989021fe9137380daf4a2a641af50f972e0989d0bb6c0609f47; complete package source hash is 98251f8e047a55a3b7161b05945c9a41d2b40e10181587a19de61e6cb3d6315c.
  - Rebuilt image sha256:6d72a620d833fbba18698bc630bb1af349d3d62be174a5f3fb064ae29335142a binds that source. Fresh dual-model CUDA smoke produced one QUALIFIED candidate from each model and the --rm container left no residue.
  - Fresh EXP-042 preflight found 24 CPUs, 25.552 GiB MemAvailable, 15272 MiB free GPU memory, no GPU compute application, no related process/container, and all domains 181-183 independently lockable.
open_risks:
  - EXP-042 remains the first run able to reach ATTEMPT_STARTED; downstream perception, planning, execution, and visual evidence remain unproven.
retained: F46 RED/GREEN/adjacent scratch, p56 including invalid first build wrapper, installed provenance, image build, smoke, preflight, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p56 after readback; no deletion authorized
decision: RUN EXP-042 with unchanged four points and physical criteria
```

## EXP-042 — Task 14 child-session-race-fixed two-Worker execute

```yaml
experiment_id: EXP-042
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T19:41:17+08:00
  - status: RUNNING
    at: 2026-09-12T19:43:05+08:00
  - status: INVALID
    at: 2026-09-12T19:46:38+08:00
prior_experiment: EXP-041
hypothesis: F46 removes the bounded parent/child setsid observation race without weakening process ownership, allowing two Workers to execute four unique points.
prediction: Four unique points finish PASSED with qualification_passed=true, each Worker handles at most two points, and every isolation, physical, visual, and cleanup invariant holds.
single_variable: F46 ProcessSupervisor child-identity read timing only. Point gates, topology, contact, reset/session, freshness, joints, goals, attachment, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f46
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f46
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: c5cc7fc987d119e4d5c15fd50635f97899448be6
  executable_source_tree: 98251f8e047a55a3b7161b05945c9a41d2b40e10181587a19de61e6cb3d6315c
  installed_module_tree: d6bc05d7f22d8989021fe9137380daf4a2a641af50f972e0989d0bb6c0609f47
  image_id: sha256:6d72a620d833fbba18698bc630bb1af349d3d62be174a5f3fb064ae29335142a
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
result: >-
  Command exit was 1 after 63.69 s. Both Workers passed stack startup, reset, and the production
  observation predicates, then failed before ATTEMPT_STARTED with POINT_INITIAL_GATE_IDENTITY.
  Source inspection proves `ParallelRosRuntime.initial_gate()` returns reset/session/time plus five
  true gate facts but omits all seven immutable lease identity fields required by
  `ParallelWorker._gate_summary`. The coordinator recorded one lease for task_start and one for
  cup_test_forward_5cm, then conservatively quarantined both Workers with terminal reason
  CAPACITY_EXHAUSTED; the other two points remained unleased. Both sealed INVALID attempt results
  state physical_action_proven_absent=true. There is no ATTEMPT_STARTED, POSE_ACCEPTED, planning,
  trajectory, or physical action evidence, so zero physical attempts are countable.
cleanup: >-
  Exact CID 8a6ad668b05d66a0a8e2ef5a9bc895547e2c56cbe3218efd4f95eca8abd1f28c
  was verified against immutable image sha256:6d72a620d833fbba18698bc630bb1af349d3d62be174a5f3fb064ae29335142a,
  batch/generation labels, and the four registered mounts, then stopped. The --rm container was
  removed; post-stop audit found no related process, running container, GPU compute task, or domain
  owner. The MuJoCo log was moved without deletion to reports/MUJOCO_LOG-EXP042.txt.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: dde91626cf6ecf60f23099074e44b76431206a87d1545bedfd7f53b82caf0d0e
command_time_sha256: 4e15056df904a9a15eb1ee3ecad6fe060b102d78635ff0ae256cde45907460cd
aggregate_sha256: dfd7f4305f057ecf9087d317e9afffe874f26d19ed9168d32ca6fdaaa83bb68b
worker_01_result_sha256: 61583c466e861851734e2f08049145f1a00faee695c85a268f2406c7459b8c62
worker_02_result_sha256: 26bb1bcb96292391c4e27a66ae059af98c6302aa96d85ddfe6ea6489ecc7db2b
mujoco_log_sha256: 3d820ff4088d4b170e23a2446241edec52c41705e320a0011382a329da701830
conclusion: INVALID; zero countable attempts. Bind the production initial-gate receipt to the exact lease under F47, retain strict Worker checks, and repeat as EXP-043.
retained: complete EXP-042 batch/reports, moved MuJoCo log, preflight, and all prior evidence
archived: none
deletion_candidates: p56/direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-027
last_valid_experiment: EXP-022
current_hypothesis: F47 supplies the exact production lease identity that the strict Worker gate already requires, allowing the unchanged four-point execute to cross ATTEMPT_STARTED without weakening authorization.
working_tree_status: clean at executable source commit f4881e44af0af7e470a71ccd1140ccb522b955d6 before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F47 formal RED pytest-IG4lggIK failed on absent production gate batch_id. Focused GREEN pytest-KTW445F6 passed and adjacent runtime/Worker pytest-zmhsPmc8 passed all 107 tests.
  - Production `initial_gate` now copies batch, coordinator epoch, Worker/generation, point, attempt, and lease generation directly from the current lease after every existing observation predicate passes. The Worker retains exact type-and-value checks against both reset and gate evidence.
  - Fresh p57 symlink build passed in 1.51 seconds. All 2771 ordinary tests passed in 83.53 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source/install module trees both hash 72b6c85efbf97cfb989519e683efebc143922c4308adb08428f04d96cf98a4a8; complete package source hash is f2d93a94041d29fba92671471ea8dc458de6303ba669ae1d6c68dfae7db40d14.
  - Rebuilt image sha256:5e77eba492f065436a078e92be217c64c0bc43f9f9b78c89544b219e470c644f binds that source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate per model.
  - Fresh EXP-043 preflight found 24 CPUs, 25.432 GiB MemAvailable, 15272 MiB free GPU, no GPU compute application, no related process/container, and all domains 181-183 independently lockable.
open_risks:
  - ATTEMPT_STARTED and downstream perception/planning/execution have not yet succeeded in a live batch.
retained: F47 RED/GREEN/adjacent scratch, p57, installed provenance, image build/smoke, EXP-043 preflight, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p57 after readback; no deletion authorized
decision: RUN EXP-043 with unchanged four points and physical criteria
```

## EXP-043 — Task 14 lease-identity-bound two-Worker execute

```yaml
experiment_id: EXP-043
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T19:51:49+08:00
  - status: RUNNING
    at: 2026-09-12T19:51:49+08:00
  - status: INVALID
    at: 2026-09-12T19:55:46+08:00
prior_experiment: EXP-042
hypothesis: F47 closes the production gate-receipt identity omission while preserving exact Worker authorization, allowing two Workers to execute four unique points.
prediction: Four unique points finish PASSED with qualification_passed=true, each Worker handles at most two points, and every isolation, physical, visual, and cleanup invariant holds.
single_variable: F47 production initial-gate receipt identity fields only. Observation predicates, Worker identity checks, topology, contact, reset/session, freshness, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f47
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f47
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: f4881e44af0af7e470a71ccd1140ccb522b955d6
  executable_source_tree: f2d93a94041d29fba92671471ea8dc458de6303ba669ae1d6c68dfae7db40d14
  installed_module_tree: 72b6c85efbf97cfb989519e683efebc143922c4308adb08428f04d96cf98a4a8
  image_id: sha256:5e77eba492f065436a078e92be217c64c0bc43f9f9b78c89544b219e470c644f
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
result: >-
  Command exit was 1 after 77.99 s before any Worker registered a lease. Worker-01's
  ros2_control_node aborted during concurrent stack initialization when controller_manager threw an
  rclcpp RCLError while sending a service response (`cannot publish data`); its joint-state and
  gripper spawners had not completed. The readiness probe consequently timed out with
  MOTION_STACK_CONTROLLER_NOT_ACTIVE. Worker-02 was stopped by conservative supervisor shutdown.
  Both Worker results are WORKER_NOT_READY, coordinator attempts are all zero, and no reset,
  ATTEMPT_STARTED, perception, planning, trajectory, or physical action occurred. This run did not
  reach the F47 variable and provides no evidence against it.
cleanup: >-
  Exact CID 372175a02a7454ecb3dd90cd3e51b6f4b24f26370674f5fcd1901eea4cd49774
  was verified against immutable F47 image, batch/generation labels, and exact registered mounts,
  then stopped. The --rm container was removed; post-stop audit found no related process, running
  container, GPU compute task, or domain owner. The MuJoCo log was moved without deletion to
  reports/MUJOCO_LOG-EXP043.txt.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 4c416ee3942a9ff627f787870dad1d6217e269897c4d45ad2827e2628dda9819
command_time_sha256: a09e5b11cc2b784ea6fc7a28ac492cbebf6de354ad5d6418b1b433d8b4bcbac1
aggregate_sha256: 88dfee692d8d7c45c51508fa715c1123b031865a4538fde8be39c19b244d21b2
worker_01_result_sha256: be7278bf3c0df75b24dbaf98581c69670cac2b89297d629c68ec6e44597c1945
worker_02_result_sha256: 08ffbab02a152ced72e6ce810b0fe9177add29f846835286af9e5927ee09e002
mujoco_log_sha256: ba8df9ac37e604b10a2eeed340f64c11f0da92fc9ac7a754c1b8d78e248cc99b
conclusion: INVALID; zero countable attempts. Preserve source, install, image, models, thresholds, and selection unchanged; repeat once from clean host state as EXP-044 rather than modifying code from a single startup middleware fault.
retained: complete EXP-043 batch/reports, moved MuJoCo log, preflight, and all prior evidence
archived: none
deletion_candidates: p57/direct pytest scratch after readback; no deletion authorized
```

## EXP-044 — Task 14 unchanged retry after isolated startup middleware fault

```yaml
experiment_id: EXP-044
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T19:56:21+08:00
  - status: RUNNING
    at: 2026-09-12T19:56:21+08:00
  - status: INVALID
    at: 2026-09-12T20:00:21+08:00
prior_experiment: EXP-043
hypothesis: EXP-043 was an isolated pre-lease controller-manager middleware fault; the unchanged F47 runtime can start both Workers and execute the four-point small batch from clean host state.
prediction: Four unique points finish PASSED with qualification_passed=true, each Worker handles at most two points, and every isolation, physical, visual, and cleanup invariant holds.
single_variable: Fresh batch/runtime identities only. Executable source, install tree, image, models, point selection, config, N=2, K=2, timeouts, point gates, and physical criteria are byte-identical to EXP-043.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f47-r2
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f47-r2
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: f4881e44af0af7e470a71ccd1140ccb522b955d6
  executable_source_tree: f2d93a94041d29fba92671471ea8dc458de6303ba669ae1d6c68dfae7db40d14
  installed_module_tree: 72b6c85efbf97cfb989519e683efebc143922c4308adb08428f04d96cf98a4a8
  image_id: sha256:5e77eba492f065436a078e92be217c64c0bc43f9f9b78c89544b219e470c644f
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
result: >-
  Command exit was 1 after 67.19 s. Unlike EXP-043, both isolated motion stacks reached READY,
  both Workers received one unique lease, reset the corresponding point, passed every production
  observation predicate, and retained immutable initial RGB evidence. Both then failed before
  ATTEMPT_STARTED with POINT_INITIAL_GATE_IDENTITY. The F47 gate receipt contains all seven exact
  lease fields, but source and sealed evidence prove production `reset_point()` still constructs a
  `ResetBoundaryReceipt` with only reset/session/time/joint data. `ParallelWorker._gate_summary`
  deliberately requires exact type-and-value identity on both reset and gate receipts, so both
  Workers were quarantined and the remaining two points stayed unleased. The two sealed INVALID
  results state physical_action_proven_absent=true. There is no ATTEMPT_STARTED, POSE_ACCEPTED,
  planning, trajectory, or physical-action evidence; the two lease counters are capacity accounting,
  not countable physical attempts.
cleanup: >-
  Exact CID f42212f1d9e6162fed2b78648ff3aa5b520424ad1dc4f6c1b3b730612c659527
  was verified against immutable image sha256:5e77eba492f065436a078e92be217c64c0bc43f9f9b78c89544b219e470c644f,
  batch/generation labels, and the four registered mounts, then stopped. The --rm container was
  removed; post-stop audit found no related process, running container, GPU compute task, or domain
  owner. The MuJoCo log was moved without deletion to reports/MUJOCO_LOG-EXP044.txt.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 8cf4a73c787eea9bbe7dbc5d8b55facec3cde271eef0506ee5e41f184ccacb11
command_time_sha256: 398a1ce39ce9b2dae546b776c5a675b4d63ddebb5d8133493b96c18b8f2cfa5e
aggregate_sha256: 51db1f329bdc0ec78d94946c73a66d57aa9ec3e1cd26da7e58dacb7c831713ff
worker_01_result_sha256: 61583c466e861851734e2f08049145f1a00faee695c85a268f2406c7459b8c62
worker_02_result_sha256: 26bb1bcb96292391c4e27a66ae059af98c6302aa96d85ddfe6ea6489ecc7db2b
mujoco_log_sha256: 0e6dbe312a8e75681598abba11d9942715632c4b05ca50872bb562d2f64e737e
conclusion: INVALID; zero countable attempts. Bind the production reset receipt to the exact lease under F48, retain strict Worker checks, and repeat only after the complete fresh build/test/image/smoke gate.
retained: complete EXP-044 batch/reports, two immutable initial RGB frames, moved MuJoCo log, preflight, and all prior evidence
archived: none
deletion_candidates: p57/direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-028
last_valid_experiment: EXP-022
current_hypothesis: F48 supplies the exact production lease identity on the reset receipt that the strict Worker gate already requires, allowing the unchanged four-point execute to cross ATTEMPT_STARTED.
working_tree_status: ledger-only result/ruling change after clean executable source f4881e44af0af7e470a71ccd1140ccb522b955d6
owned_processes: NONE
confirmed_conclusions:
  - EXP-044 started two isolated stacks cleanly, reached READY, reset two unique points, and passed all initial observation predicates; the EXP-043 middleware fault did not recur.
  - Each Worker consumed one lease capacity slot but neither journal nor sealed evidence contains ATTEMPT_STARTED; physical_action_proven_absent is true and zero physical attempts are countable.
  - F47 correctly binds all seven exact identity fields to the gate receipt. Production reset_point returns a ResetBoundaryReceipt without those fields, while the Worker intentionally requires both receipts to match the lease exactly.
  - Exact Broker cleanup completed and audits found no related process, container, GPU compute task, or domain owner.
open_risks:
  - ATTEMPT_STARTED and downstream perception/planning/execution have not yet succeeded in a live batch.
ruling: F48 may only add the seven immutable current-lease identity fields to the production ResetBoundaryReceipt returned by reset_point, without changing reset semantics, gate predicates, Worker checks, topology, timeouts, models, selection, or physical criteria. Formal RED must exercise the production reset path and fail on the absent fields; GREEN must prove exact type and value for all seven fields and preserve existing reset receipt validation.
retained: complete EXP-044 evidence and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p57 after readback; no deletion authorized
decision: IMPLEMENT F48 WITH FORMAL RED/GREEN
```

```yaml
checkpoint_id: CP-029
last_valid_experiment: EXP-022
current_hypothesis: F48 closes the complementary reset-receipt lease-identity omission, allowing the unchanged four-point execute to cross ATTEMPT_STARTED without weakening authorization.
working_tree_status: clean at executable source commit b7a6e99cf969f1e1ff3bd87a0e44bb7af9376921 before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F48 formal RED pytest-HhpjwIz1 failed on absent production reset receipt batch_id. Focused GREEN pytest-vtEjq3ro passed, and the correctly sourced adjacent runtime/Worker gate pytest-NykRKYVs passed all 156 tests.
  - Production reset_point now copies batch, coordinator epoch, Worker/generation, point, attempt, and lease generation directly from the current lease into ResetBoundaryReceipt. Reset behavior and strict Worker checks are unchanged.
  - pytest-1c01GhsK and p58 are retained as invalid harness-environment attempts: each omitted the locked ML path or correct overlay/result scope; neither reports a product failure.
  - Fresh p59 symlink build passed in 1.51 seconds. All 2771 ordinary tests passed in 82.42 seconds pytest and 84.11 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source/install module trees both hash 04735643c65be3e568964c83b75e39c50e6f75c527209e4a62ff88771cad8231; complete package source hash is 9e7451a932cadd923b445e09b91dd76867789337e6c943cc5df88e87215c4173.
  - Rebuilt image sha256:f05493c493c62d45a8d393e87ef5034bc88de622098a3be2f49578c0cc524bb8 binds that source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate per model: YOLO 37.61 ms and Grounded-SAM 187.07 ms.
  - Fresh EXP-045 preflight found 24 CPUs, 25.459 GiB MemAvailable, 15272 MiB free GPU, no GPU compute application, no related running process/container, and all domains 181-183 independently lockable.
open_risks:
  - ATTEMPT_STARTED and downstream perception/planning/execution have not yet succeeded in a live batch.
retained: F48 RED/GREEN/adjacent scratch, invalid environment runs, p58/p59, provenance reports including failed empty outputs, image build/smoke, EXP-045 preflight attempts, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p59 after readback; no deletion authorized
decision: RUN EXP-045 with unchanged four points and physical criteria
```

## EXP-045 — Task 14 reset-and-gate lease-identity-bound two-Worker execute

```yaml
experiment_id: EXP-045
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T20:18:48+08:00
  - status: RUNNING
    at: 2026-09-12T20:22:42+08:00
  - status: INVALID
    at: 2026-09-12T20:24:11+08:00
prior_experiment: EXP-044
hypothesis: F48 supplies exact current-lease identity on both production reset and gate receipts, allowing two Workers to execute four unique points.
prediction: Four unique points finish PASSED with qualification_passed=true, each Worker handles at most two points, and every isolation, physical, visual, and cleanup invariant holds.
single_variable: F48 production reset-receipt identity fields only. Reset behavior, gate predicates, Worker identity checks, topology, contact, freshness, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f48
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f48
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: b7a6e99cf969f1e1ff3bd87a0e44bb7af9376921
  executable_source_tree: 9e7451a932cadd923b445e09b91dd76867789337e6c943cc5df88e87215c4173
  installed_module_tree: 04735643c65be3e568964c83b75e39c50e6f75c527209e4a62ff88771cad8231
  image_id: sha256:f05493c493c62d45a8d393e87ef5034bc88de622098a3be2f49578c0cc524bb8
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp045-r3.json; earlier empty preflight-exp045.json and preflight-exp045-r2.json are retained invalid wrapper outputs and are not authorities
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
result: >-
  Command exit was 1 after 88.72 s. Both Workers started, received one distinct lease, reset their
  points, passed the exact F48 reset/gate identity checks, and durably ACKed ATTEMPT_STARTED. Both
  immutable initial frames were inspected at original 640x480 resolution and show the commanded cup
  position, canonical reset arm, clear gripper/cup separation, and no visible penetration. Both
  first YOLO requests then terminated INVALID/PERCEPTION_INFRA_ERROR before pose admission or any
  controller command; sealed results independently state physical_action_proven_absent=true. The
  shared deterministic cause is that capture_rgb used `mkdir(parents=True, mode=0700)` for the
  Broker mirror: only the leaf received 0700, while every newly created intermediate beneath the
  pre-existing 0700 broker-inputs root is owner 1000:1000 mode 0775 under host umask 0002. The
  Broker correctly rejects any group/other-writable parent with INPUT_DIRECTORY_OWNER_MODE. The two
  ATTEMPT_STARTED records consume one K unit on each Worker; the remaining two points were never
  leased. Recovery was conservatively unsuccessful; one replacement ros2_control_node also
  reproduced the known service-response RCLError during shutdown/start overlap, after both
  perception outcomes, and is not their cause.
cleanup: >-
  Exact CID b8e1b205c45df08366c5e11d760680a33b312b049235f1de20a9427a55f2d037
  was verified against immutable F48 image, exact batch/generation labels, and the four registered
  mounts, then stopped. The --rm container was removed; post-stop audits found no related owned
  process, running batch container, GPU compute task, or domain owner. The MuJoCo log was moved
  without deletion to reports/MUJOCO_LOG-EXP045.txt.
visual_sha256:
  cup_test_forward_5cm: fad007b56ded2b87722b56a2c926d8e16612a09d9daeabdca4be3481df382f3d
  task_start: b2870627e9c2fe521bb8e8204c323dc9e10e7aed8e9919ffaba7bb28946ba05f
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 27ac60a1e7e764687daa0eadf7fc4bdfbcb5a99ff2aa7f1d5d0500552bde5f33
command_time_sha256: df5438fee6f2abc958fb2b0fe4984534e818d1b5c36bca958bcda95975dc2ce0
aggregate_sha256: a646b1d3e05e4f44fa67c5199fe9b2a06c964f96982e980add3aab32dbd9fe03
worker_01_result_sha256: 85c5236332e7d1fbe47c921384cf49c1dc89892456dced5829c93cde5130257c
worker_02_result_sha256: 4b2eb091d2844f41c40732a3671ca32cc81141ea251f956ce0431055de7371ae
mujoco_log_sha256: 5d3e2ba97e711cd4893244b273b852a9c2fa2097c0e6414d663aa3ba9525766f
conclusion: INVALID infrastructure result after two durable ATTEMPT_STARTED records; zero physical actions. Keep the Broker security gate strict, create every mirror directory privately under F49, rebuild, and restart the complete four-point validation with a new batch identity.
retained: complete EXP-045 batch/reports, two visually inspected immutable initial RGB frames, moved MuJoCo log, F48 qualification evidence, preflight-exp045-r3.json, and all prior evidence
archived: none
deletion_candidates: p58/p59 and direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-030
last_valid_experiment: EXP-022
current_hypothesis: Exact 0700 creation of every Broker mirror directory will preserve the security boundary and allow the two authorized YOLO requests to execute.
working_tree_status: ledger-only EXP-045 result and F49 ruling after clean executable source b7a6e99cf969f1e1ff3bd87a0e44bb7af9376921
owned_processes: NONE
confirmed_conclusions:
  - EXP-045 proves F48 in production: both exact reset/gate identities passed and two distinct ATTEMPT_STARTED records were durable.
  - Both point results are INVALID/PERCEPTION_INFRA_ERROR with physical_action_proven_absent=true; no pose admission, plan, trajectory, or controller action exists.
  - Every intermediate Broker mirror directory created by pathlib parents=True is mode 0775 under umask 0002, while the input leaf is 0700 and RGB file is owner 1000:1000 mode 0400 with the sealed hash.
  - ParallelPerceptionRuntime deliberately rejects group/other-writable parents. F49 will fix the producer and retain that security check unchanged.
  - Both original-resolution initial frames were completely inspected and are visually consistent with the reset point and absence of contact or penetration.
  - Exact Broker cleanup completed and no related owned process, running batch container, GPU compute task, or domain owner remained.
open_risks:
  - Perception, pose admission, planning, and execution have not yet succeeded in a live batch.
retained: complete EXP-045 evidence, moved MuJoCo log, all F48 evidence, invalid harness outputs, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p59 after readback; no deletion authorized
decision: IMPLEMENT F49 WITH FORMAL RED/GREEN
```

```yaml
checkpoint_id: CP-031
last_valid_experiment: EXP-022
current_hypothesis: F49 preserves the strict Broker path boundary while allowing authorized immutable RGB inputs to reach both frozen perception models.
working_tree_status: clean at executable source commit 1dd480a2fbef595f7a95cce81d8c779d5f22de1b before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F49 formal RED pytest-e2i7E9a3 failed because umask 0002 produced owner 1000:1000 mode 0775 intermediate mirror directories. Focused GREEN pytest-3Qo0Y7l8 passed, and adjacent runtime tests pytest-SVXvYL4k passed all 157 tests.
  - ParallelRosRuntime now creates each directory below the private broker-inputs root sequentially and verifies regular directory type, non-symlink identity, current UID ownership, and exact mode 0700 before linking the immutable RGB. Broker read-only, owner, mode, and hash checks are unchanged.
  - Fresh p64 build passed in 1.51 seconds. All 2772 ordinary tests passed in 82.11 seconds pytest and 83.80 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source/install module trees both hash 57d1af0940fb897c9fd3aec4c793aa93241a22f0c9d762de614e509f558b755d; complete package source hash is 21d9f8f335e40f55d63807ae96fd4e56927eb0380586a7965c2497eb2e599226.
  - Rebuilt image sha256:a51fde9d37f67be73acb24691e57935a25d712fdb98aea98e06574ba3443ba4e binds that source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate per model: YOLO 36.94 ms and Grounded-SAM 196.89 ms. Exact smoke CID 02da284627d234ae068f351ddd27a0818e3a076da23cbf0e18f983a1dcf83c06 was absent after --rm.
  - Frozen plan, design, and catalog hashes remain exact. Fresh EXP-046 preflight found 24 CPUs, 25.525 GiB MemAvailable, 15272 MiB free GPU, no GPU compute application, related process, or running related container, and all domains 181-183 independently lockable.
  - p61-p63 and the first four F49 smoke wrappers are retained as invalid harness/argument attempts; none started tests or a container except the final successful smoke. p64 is the authoritative complete gate.
open_risks:
  - Live perception, pose admission, planning, and physical execution have not yet succeeded.
retained: F49 RED/GREEN/adjacent scratch and logs, p61-p64 wrapper/build/test evidence, installed provenance, image build, all smoke attempts and successful smoke root, EXP-046 preflight, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p64 after readback; no deletion authorized
decision: RUN EXP-046 with unchanged four points and physical criteria
```

## EXP-046 — Task 14 private-Broker-input two-Worker execute

```yaml
experiment_id: EXP-046
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T21:44:57+08:00
  - status: RUNNING
    at: 2026-09-12T21:48:44+08:00
  - status: INVALID
    at: 2026-09-12T21:54:31+08:00
prior_experiment: EXP-045
hypothesis: F49 exact 0700 mirror construction allows both authorized perception requests through the unchanged Broker security gate and permits four unique points to execute.
prediction: Four unique points finish PASSED with qualification_passed=true, each Worker handles at most two points, and every isolation, physical, visual, and cleanup invariant holds.
single_variable: F49 private Broker mirror directory creation and verification only. Broker checks, reset/gate identity, topology, contact, freshness, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f49
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f49
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 1dd480a2fbef595f7a95cce81d8c779d5f22de1b
  executable_source_tree: 21d9f8f335e40f55d63807ae96fd4e56927eb0380586a7965c2497eb2e599226
  installed_module_tree: 57d1af0940fb897c9fd3aec4c793aa93241a22f0c9d762de614e509f558b755d
  image_id: sha256:a51fde9d37f67be73acb24691e57935a25d712fdb98aea98e06574ba3443ba4e
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp046.json; sha256 2dfa89ce25c61e87afb99ed38bc5afa6f165490136021c9ff8db99813b0dd9d7
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-small-20260912-v1-f49 --worker-count 2 --max-points-per-worker 2 --evidence-root /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f49 --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
acceptance: The complete frozen Task 14 live-small gate; INVALID infrastructure outcomes remain non-qualifying and receive a fresh batch ID after root-cause correction.
result: >-
  Command exit was 1 after 44.52 seconds. Both Workers received distinct leases, passed reset and
  point-initial gates, durably ACKed ATTEMPT_STARTED, and produced immutable RGB plus Broker mirror
  NPY evidence. Every directory in both Broker mirror chains is owner 1000:1000 mode 0700 and both
  linked RGB inputs passed the producer identity/hash checks, proving F49 fixed EXP-045's exact
  defect without relaxing the Broker. Both requests then sealed INVALID/PERCEPTION_INFRA_ERROR
  within about 0.08 seconds of ATTEMPT_STARTED, before any model result, pose admission, plan,
  trajectory, or controller action. Existing post-authorization Worker handling deliberately maps
  every caught exception to the same conservative attempt result and discards its boundary/type/text;
  therefore current durable evidence cannot distinguish Broker authentication, authorization,
  frame validation, or RPC response rejection. Both physical_action_proven_absent values are true,
  the two started attempts consume one K unit per Worker, and the remaining points were never leased.
cleanup: >-
  Exact CID 022dc3b80343821a98bacc59e36016ad6c99c23ff5155b4ec27f6b57b3d66101
  was verified against immutable F49 image, exact batch/generation labels, and the four registered
  mounts, then stopped; delayed --rm removal was independently read back. Final audit found empty
  coordinator/Worker ownership manifests, no related process or container, no GPU compute task, and
  no same-UID domain 181-183 owner. The MuJoCo log was moved without deletion to
  reports/MUJOCO_LOG-EXP046.txt.
visual_sha256:
  cup_test_forward_5cm: de0090ccb960d7f6c7d855b6c33c4c3ceacc3eaf3f640e04e455c25a977f9e89
  task_start: 5a772f4ffcd9d4880ae8bb9c49b7df42edee29f9691f69f7bdf083e1fba2dce7
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: f74ecadd840003768d0b87518c237a3396ea76e22077f2a40f9c22bc074ad2e1
command_time_sha256: 5c425bdeb88b87bf21e2dda0423b9c76bb9590f52e7b8f0698c44cb683bda989
aggregate_sha256: 556aaafed719472b8be5f06faf8bc804e4a4a080933a3f579f3e46488eace72d
coordinator_aggregate_sha256: 9de23b73a53c3ed9dabd4cf167b831a4c2acb2abfb500315a16f4268f5d5b9f5
worker_01_result_sha256: 85c5236332e7d1fbe47c921384cf49c1dc89892456dced5829c93cde5130257c
worker_02_result_sha256: 4b2eb091d2844f41c40732a3671ca32cc81141ea251f956ce0431055de7371ae
mujoco_log_sha256: eaa4dcfaca52a1effb1ad2a2e8c513f479c0e7671d3797673b96f6197b20d860
post_cleanup_sha256: dd9cbea1085fd24ab22eb48f1a663f0df47d90628e2ce6c02a9149c0e624ab97
conclusion: INVALID infrastructure result after two durable ATTEMPT_STARTED records; zero physical actions. Add bounded post-authorization boundary/type/message evidence without changing the conservative result, then repeat with a new batch identity after full qualification.
retained: complete EXP-046 batch/reports, two visually inspected immutable initial RGB frames and NPY mirrors, moved MuJoCo log, all cleanup evidence, and all prior evidence
archived: none
deletion_candidates: p61-p64 and direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-032
last_valid_experiment: EXP-022
current_hypothesis: A bounded phase-specific diagnostic on the already-conservative post-authorization failure path will identify the immediate request-layer defect without changing authorization, result status, recovery, or physical behavior.
working_tree_status: ledger-only EXP-046 result and F50 ruling after clean executable source 1dd480a2fbef595f7a95cce81d8c779d5f22de1b
owned_processes: NONE
confirmed_conclusions:
  - EXP-046 crossed both reset/gate identity checks and durable ATTEMPT_STARTED on two distinct points; both attempts ended before pose admission with physical_action_proven_absent=true.
  - F49 is proven in production: all fourteen created intermediate/leaf directories across both Broker input paths are exact mode 0700, and each immutable NPY mirror has the sealed content hash.
  - Both failures occurred immediately after authorization entered EXECUTING. The Broker produced no model result, while current _run_authorized catches and discards every exception before returning the generic conservative decision.
  - Both original-resolution initial frames were completely inspected and show correct cup placement, canonical reset posture, and no visible contact or penetration.
  - Exact Broker cleanup completed and no related owned process, running batch container, GPU compute task, or domain owner remained.
open_risks:
  - The exact request-layer exception is not recoverable from EXP-046 because the production diagnostic seam discards it by design.
ruling: F50 may only add a fixed phase label plus bounded exception type/message to WorkerRunResult when _run_authorized catches an exception. It must preserve the existing INVALID/INDETERMINATE decision, AUTHORIZATION_OR_PORT_FAILURE reason, safe-stop ordering, sealing, commit, recovery, authorization, timeouts, and all physical/model criteria. Formal RED/GREEN must cover inference_snapshot, request_model, admit_pose, and execute/plan boundaries and prove 512-byte single-line bounding.
retained: complete EXP-046 evidence, cleanup audit, all F49 evidence, invalid wrapper outputs, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p64 after readback; no deletion authorized
decision: IMPLEMENT F50 DIAGNOSTICS WITH FORMAL RED/GREEN
```

```yaml
checkpoint_id: CP-033
last_valid_experiment: EXP-022
current_hypothesis: F50 will retain the exact post-authorization request exception needed to select a narrow corrective variable while preserving fail-closed behavior.
working_tree_status: clean at executable source commit 42a7306ec99d720638925c8b286a3003ff65efe1 before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F50 formal RED pytest-GGQMNU0y failed all five expected diagnostic assertions. Focused GREEN pytest-xFd6ynLY passed all five, and adjacent Worker/CLI gate pytest-OOrWduG7 passed all 159 tests.
  - WorkerRunResult now identifies inference_snapshot, request_model, admit_pose, execute_expert, or plan_expert and carries a 128-character type plus single-line 512-byte UTF-8-safe message. Existing safe-stop order, durable result reason/status, recovery, and physical-action semantics are unchanged.
  - Fresh p65 build passed in 1.52 seconds. All 2777 ordinary tests passed in 81.97 seconds pytest and 83.67 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source/install module trees both hash 21a0461b4d71b58f179402536c72b790ba130a48f4e20bd676c2d45b1a69e59f; complete package source hash is 55ad0033ad9e0b0ec80a8897875713695eb236788b6d13185619b6195b30ae94.
  - Rebuilt image sha256:22b83823ab900cc478fc9d492df55bbce20d4b2a8e5f172c50b5c6e743f40e9b binds that source and passed fresh dual-model CUDA smoke with one QUALIFIED candidate per model: YOLO 35.85 ms and Grounded-SAM 191.84 ms. Exact smoke CID 8d1fc63d0db092587e7604364db2af23f8c367f8f495d6c57476f7031bb5ec79 was absent after --rm.
  - Fresh EXP-047 preflight found 24 CPUs, 25.412 GiB MemAvailable, 15269 MiB free GPU, no GPU compute application, related process, or running related container, and all domains 181-183 independently lockable.
open_risks:
  - The exact request-layer exception still requires one fresh live run to observe.
retained: F50 RED/GREEN/adjacent scratch and logs, p65 including invalid first test-result wrapper and valid r2 readback, provenance, image build/smoke, EXP-047 preflight, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p65 after readback; no deletion authorized
decision: RUN EXP-047 with unchanged four points and physical criteria
```

## EXP-047 — Task 14 bounded request-diagnostic two-Worker execute

```yaml
experiment_id: EXP-047
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T22:08:26+08:00
  - status: RUNNING
    at: 2026-09-12T22:10:00+08:00
  - status: INVALID
    at: 2026-09-12T22:14:27+08:00
prior_experiment: EXP-046
hypothesis: F50 will identify the exact post-authorization request boundary and exception while leaving the two-Worker runtime otherwise identical.
prediction: Either four unique points finish PASSED with full qualification, or every failure retains a bounded exact diagnostic sufficient for one narrow next fix and proves physical safety.
single_variable: F50 bounded WorkerRunResult diagnostic only. Authorization, Broker checks, reset/gate identity, topology, contact, freshness, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f50
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f50
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown; otherwise exact bounded post-authorization diagnostics with no unproven physical action.
provenance:
  executable_source_commit: 42a7306ec99d720638925c8b286a3003ff65efe1
  executable_source_tree: 55ad0033ad9e0b0ec80a8897875713695eb236788b6d13185619b6195b30ae94
  installed_module_tree: 21a0461b4d71b58f179402536c72b790ba130a48f4e20bd676c2d45b1a69e59f
  image_id: sha256:22b83823ab900cc478fc9d492df55bbce20d4b2a8e5f172c50b5c6e743f40e9b
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp047.json; sha256 6e49c7b712c27ede8be37a8ff27e7f2832d7b73bac2d0c01ced736a9ff09157b
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-small-20260912-v1-f50 --worker-count 2 --max-points-per-worker 2 --evidence-root /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f50 --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
acceptance: The complete frozen Task 14 live-small gate; any diagnostic failure remains INVALID and non-qualifying.
result: >-
  Command exit was 1 after 53.67 seconds. Worker-01 failed the point-initial graph gate before
  ATTEMPT_STARTED because /so101_base_to_camera_link was absent from its stable sample; no RGB or
  physical action followed for that Worker. Worker-02 passed the gate, durably ACKed
  ATTEMPT_STARTED, created an exact 0700 Broker mirror chain, and completed a Broker RPC. The
  response outcome was INFRA_ERROR rather than an exception: run_perception_chain converted it to
  the unchanged PERCEPTION_INFRA_ERROR terminal, so the F50 exception fields correctly remained
  null. The Broker response's reason is not currently projected into any durable Worker field,
  leaving the exact frame/model cause unavailable after shutdown. worker-02 sealed
  physical_action_proven_absent=true; no pose admission, plan, trajectory, or controller action
  occurred. The two started/failed leases exhausted both Workers and the remaining points were not
  leased.
cleanup: >-
  Exact CID d386d4523ed9c182ee8bdb56cd3b0f13bc0d6f481b9ca42f6f9651f75f659c34
  was verified against immutable F50 image, exact batch/generation labels, and registered mounts,
  then stopped and independently observed removed by --rm. Final audit found empty ownership
  manifests, no related process or container, no GPU compute task, and no same-UID domain 181-183
  owner. The MuJoCo log was moved without deletion to reports/MUJOCO_LOG-EXP047.txt.
visual_sha256:
  task_start: 1c720010f645481f85786c9b8e63615ab96ad2ae2818f810f87545cb0d51f343
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: de14b2b8d7c573fea4ae78e06673ad90a8e3912277e3078deffa27fc98a06a3a
command_time_sha256: 1476c7d2a493a729bdb3d601a77fb2aa2caa15776d1bbc415922327674a810d8
aggregate_sha256: 556aaafed719472b8be5f06faf8bc804e4a4a080933a3f579f3e46488eace72d
coordinator_aggregate_sha256: 3ae39755abe895e746ccf2e7485ec8dd5dae30427ee38c6364d44764e77b324e
worker_01_result_sha256: a6ad0d293f92ecbc2e31dc14bdbaa0bff795a1c0b0f8c61fcb8acbf76f711746
worker_02_result_sha256: 4b2eb091d2844f41c40732a3671ca32cc81141ea251f956ce0431055de7371ae
mujoco_log_sha256: 0b449c36f52dcc764120d71b1c27938b49fb1b75914a3b2743cbf6a39fb8bd41
post_cleanup_sha256: ec2f2ca2f4c6e7bd27d9c6f5c9917fbf85a6adba55fc94924ab3cb913bc435af
conclusion: INVALID diagnostic infrastructure result; zero physical actions. Preserve the Broker response reason in bounded Worker diagnostics under F51, then repeat with a new batch identity after complete qualification.
retained: complete EXP-047 batch/reports, the one authorized and visually inspected immutable initial RGB, moved MuJoCo log, cleanup evidence, and all prior evidence
archived: none
deletion_candidates: p65 and direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-034
last_valid_experiment: EXP-022
current_hypothesis: A bounded diagnostic projection of BrokerResponse outcome/reason will expose the exact model infrastructure rejection without altering the conservative perception terminal or attempt result.
working_tree_status: ledger-only EXP-047 result and F51 ruling after clean executable source 42a7306ec99d720638925c8b286a3003ff65efe1
owned_processes: NONE
confirmed_conclusions:
  - Worker-02 completed a Broker RPC and received ModelOutcome.INFRA_ERROR; this was not an exception, so F50 correctly did not fabricate exception diagnostics.
  - run_perception_chain has the exact BrokerResponse.reason but returns only the generic policy terminal; the unchanged execute adapter then seals PERCEPTION_INFRA_ERROR.
  - Worker-01 independently failed the strict graph gate on missing /so101_base_to_camera_link before ATTEMPT_STARTED, with no captured RGB or physical action.
  - The only authorized original-resolution frame was inspected and is visually consistent with reset and no contact or penetration.
  - Exact Broker cleanup completed and no related owned process, running batch container, GPU compute task, or domain owner remained.
open_risks:
  - Exact Broker response reason is not present in current durable evidence.
  - The point-initial graph can still sample a transient missing fixed camera node.
ruling: F51 may add optional diagnostic type/message fields to PerceptionTerminal and copy only an infrastructure BrokerResponse outcome/reason into them, then project those fields through the existing F50 WorkerRunResult boundary using the same 128-character type and 512-byte single-line UTF-8 limits. It must preserve PerceptionTerminal disposition/reason, attempt status/reason, model sequence, safe-stop, authorization, and physical behavior. Formal RED/GREEN must prove exact projection and that normal rejection/success do not fabricate diagnostics.
retained: complete EXP-047 evidence, cleanup audit, all F50 evidence, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p65 after readback; no deletion authorized
decision: IMPLEMENT F51 BROKER RESPONSE DIAGNOSTICS WITH FORMAL RED/GREEN
```

```yaml
checkpoint_id: CP-035
last_valid_experiment: EXP-022
current_hypothesis: F51 exposes the exact Broker infrastructure response reason needed for a narrow correction while preserving all result and safety semantics.
working_tree_status: clean at executable source commit 9c6d36f4822b6795d779f85b8a71535a3162184f before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F51 formal RED pytest-TprOrPop failed all three expected diagnostic assertions. Focused GREEN pytest-JEoIISdq passed all three; correctly sourced adjacent gate pytest-G8ygDbhE passed all 193 tests. pytest-O0Xr9kdP is retained as an invalid old-overlay environment attempt.
  - PerceptionTerminal now retains only infrastructure BrokerResponse outcome/reason as optional diagnostics. Worker projects them through F50's fixed request_model boundary and bounds while the generic perception terminal and persistent attempt reason remain unchanged. Normal rejection does not fabricate diagnostics.
  - Fresh p66 build passed in 1.50 seconds. All 2780 ordinary tests passed in 88.50 seconds pytest and 90.19 seconds wall with zero errors, failures, or skips and no benchmark collection.
  - Source/install module trees both hash cb0325cf78d6d18413ec15a4fc33bfe147b26eff04ec5fefeac07027de5384e1; complete package source hash is 08148d13761feb753a85a59ea1b7d6deed945d48ec5f302d744ec172f4b4d92a.
  - Rebuilt image sha256:36bd327006f8bd8cc93b3c69da0bee0407ce7a9c430d0f0e65fd2b98f2d6a18e binds that source and passed dual-model CUDA smoke with one QUALIFIED candidate per model: YOLO 36.79 ms and Grounded-SAM 194.22 ms. Exact smoke CID 610e558448ae50eb1170ab060a5b5039fed124fd60b9b57de6d0c8c7ea6dd1c4 was absent after --rm.
  - Fresh EXP-048 preflight found 24 CPUs, 25.364 GiB MemAvailable, 15269 MiB free GPU, no GPU compute application, related process, or running related container, and all domains 181-183 independently lockable.
open_risks:
  - One fresh live run is required to observe the exact Broker infrastructure reason.
  - The point-initial graph can still sample a transient missing fixed camera node.
retained: F51 RED/GREEN/adjacent scratch and logs, p66, provenance, image build/smoke, EXP-048 preflight, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p66 after readback; no deletion authorized
decision: RUN EXP-048 with unchanged four points and physical criteria
```

## EXP-048 — Task 14 Broker-response-diagnostic two-Worker execute

```yaml
experiment_id: EXP-048
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T22:20:27+08:00
  - status: RUNNING
    at: 2026-09-12T22:22:00+08:00
  - status: INVALID
    at: 2026-09-12T22:25:47+08:00
prior_experiment: EXP-047
hypothesis: F51 will preserve the exact Broker infrastructure response reason while leaving the two-Worker runtime otherwise identical.
prediction: Either four unique points finish PASSED with full qualification, or every Broker infrastructure result retains a bounded exact reason sufficient for one narrow next fix and proves physical safety.
single_variable: F51 bounded BrokerResponse diagnostic only. Authorization, Broker checks, reset/gate identity, topology, contact, freshness, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f51
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f51
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown; otherwise exact bounded Broker diagnostics with no unproven physical action.
provenance:
  executable_source_commit: 9c6d36f4822b6795d779f85b8a71535a3162184f
  executable_source_tree: 08148d13761feb753a85a59ea1b7d6deed945d48ec5f302d744ec172f4b4d92a
  installed_module_tree: cb0325cf78d6d18413ec15a4fc33bfe147b26eff04ec5fefeac07027de5384e1
  image_id: sha256:36bd327006f8bd8cc93b3c69da0bee0407ce7a9c430d0f0e65fd2b98f2d6a18e
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp048.json; sha256 ec1b52c188d5231fd55218d46ee1f87adf8bf1b6690ac515eaf48695fafbbaff
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-small-20260912-v1-f51 --worker-count 2 --max-points-per-worker 2 --evidence-root /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f51 --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
acceptance: The complete frozen Task 14 live-small gate; any diagnostic failure remains INVALID and non-qualifying.
result: >-
  Command exit was 1 after 55.00 seconds. Both Workers passed their exact reset and point-initial
  gates, durably ACKed ATTEMPT_STARTED, created owner-only Broker input mirrors, and completed an
  authenticated Broker RPC. F51 preserved the identical bounded result on both Workers:
  failure_boundary=request_model, failure_type=BrokerResponse.INFRA_ERROR, and
  failure_message=BROKER_NOT_READY. The unchanged attempt result remained
  PERCEPTION_INFRA_ERROR with physical_action_proven_absent=true. No pose admission, plan,
  trajectory, controller goal, or physical action occurred; the remaining two points were never
  leased. The model-ready and strict ready receipts both prove both CUDA models loaded. Source
  inspection then closed the lifecycle cause: container_main starts ParallelPerceptionRuntime
  before transport.serve constructs PerceptionService and installs its health_changed callback;
  service.start calls the already-started runtime, whose healthy idempotent branch returns without
  replaying ready state, so PerceptionBroker retains both models as not ready.
cleanup: >-
  Exact CID f4c4fe5fc8ede9b746e609c1aaffef1f7299bcfd2d280110e1e7675736f91edd
  was verified against immutable F51 image, exact batch/generation labels, and registered mounts,
  then stopped and independently observed removed by --rm. Final readback found no related process
  or container and all domains 181-183 independently lockable. The MuJoCo log was moved without
  deletion to reports/MUJOCO_LOG-EXP048.txt.
visual_observation: >-
  Both immutable 640x480 initial RGB files were inspected at original resolution. task_start and
  cup_test_forward_5cm show their expected distinct cup positions and canonical initial arm state;
  neither image shows robot-object contact or visible penetration.
visual_sha256:
  task_start: 1c720010f645481f85786c9b8e63615ab96ad2ae2818f810f87545cb0d51f343
  cup_test_forward_5cm: fad007b56ded2b87722b56a2c926d8e16612a09d9daeabdca4be3481df382f3d
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: cceeb1dcf002fdfefe850406f59156887ce32c20afd2463b26de4ce51a49fa22
command_time_sha256: 9ecaf308fafc3aa62ae1a4b8d8802e42daf232eb8f8d4c2f6ed0a798e7b074ef
aggregate_sha256: 556aaafed719472b8be5f06faf8bc804e4a4a080933a3f579f3e46488eace72d
coordinator_aggregate_sha256: 8ea710c3dd47d64e6ad0d38c768ccc08b1e9b0f9105a31fd1980d3fdd509ff35
worker_01_result_sha256: 1987f29d25168af4fe6853d11ca2e2ccd2cffbdb0ca31eddb66f0c88d36e32f1
worker_02_result_sha256: 66eaaac2f130656e4d0564e5a9a807aab8d3b747963071680453f79cd2d79b30
mujoco_log_sha256: 5dd6ed3cf7a82236970abb96b4550ad31a5f9bdf5a3e278cfdab9fba94f2dbdc
broker_inspect_sha256: bf162f03298ade9e8952db9d6baba43d62ba6d424b07f104c6fa2cce5c045bc7
broker_log_sha256: 01fcc26c9ae6f418d6fe935ea91b0c6017925c9c82cb59da7b8499594f6c64d3
post_cleanup_sha256: bd07c564e1e6c7c24163325827c58f86677c58c39c8761c7e042197633dddd50
conclusion: INVALID diagnostic infrastructure result; zero physical actions. Implement F52 as ready-state replay only, qualify completely, then repeat with a new batch identity.
retained: complete EXP-048 batch/reports, both authorized and visually inspected immutable initial RGB files, moved MuJoCo log, cleanup evidence, and all prior evidence
archived: none
deletion_candidates: p66 and direct pytest scratch after readback; no deletion authorized
```

```yaml
checkpoint_id: CP-036
last_valid_experiment: EXP-022
current_hypothesis: Replaying the current healthy state when an already-started runtime receives a new lifecycle observer will make both Broker models ready without changing inference, authorization, or failure semantics.
working_tree_status: ledger-only EXP-048 result and F52 ruling after clean executable source 9c6d36f4822b6795d779f85b8a71535a3162184f
owned_processes: NONE
confirmed_conclusions:
  - Both EXP-048 Workers passed the exact lease-bound reset and graph gates and crossed durable ATTEMPT_STARTED before receiving the same authenticated BrokerResponse.INFRA_ERROR reason BROKER_NOT_READY.
  - Both model-ready receipts prove successful CUDA model startup, while the Broker's own model readiness remained false.
  - container_main starts the runtime before transport.serve creates PerceptionService. PerceptionService replaces health_changed only after that first healthy transition, then its service.start reaches the idempotent runtime.start branch, which returns without notifying the new observer.
  - Both original-resolution images are visually consistent with their frozen points and show no contact or penetration; sealed attempt results prove physical_action_proven_absent=true.
  - Exact Broker cleanup completed and no related owned process, running batch container, or domain owner remained.
open_risks:
  - The ready-state replay path is not covered by a regression test.
  - A fresh live-small run is required after qualification to prove the Broker admits both models.
ruling: F52 may make the healthy idempotent ParallelPerceptionRuntime.start branch invoke health_changed(true) before returning. It must not rebuild detectors, rewrite the ready receipt, weaken restart-required behavior for unhealthy runtimes, alter Broker policy, or change authorization, inference, attempt, safe-stop, or physical semantics. Formal RED/GREEN must prove late observer replay, no detector rebuild or receipt rewrite, and unchanged unhealthy restart rejection.
retained: complete EXP-048 evidence, cleanup audit, all F51 evidence, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p66 after readback; no deletion authorized
decision: IMPLEMENT F52 READY-STATE REPLAY WITH FORMAL RED/GREEN
```

```yaml
checkpoint_id: CP-037
last_valid_experiment: EXP-022
current_hypothesis: The qualified F52 image will admit both models through the production Broker and advance the unchanged four-point execute beyond perception.
working_tree_status: clean at executable source commit 328de1909c6b7ceb19b2d5b6ac9a41e0e7888b69 before this ledger-only pre-run commit
owned_processes: NONE
confirmed_conclusions:
  - F52 formal RED pytest-AUukJVTd failed the expected late-observer assertion while the unhealthy restart guard passed. Focused GREEN pytest-1kH5Lg9T passed 2/2 and adjacent pytest-rKbdK13t passed 203/203.
  - The healthy idempotent start path now invokes health_changed(true). Tests prove no detector rebuild, no ready-receipt byte or mtime change, and unchanged RESTART_REQUIRED behavior for an unhealthy started runtime.
  - Fresh p67 build passed in 1.51 seconds. The first p67 test attempt is retained as an invalid missing-locked-ML-path harness attempt. Correctly phase-separated p68 passed all 2782 ordinary tests in 82.71 seconds pytest and 84.42 seconds wall; exact package test-result reports zero errors, failures, or skips and benchmark_test was not collected. The unscoped p68 test-result invocation is retained as invalid because it included stale unrelated so101_teleop JUnit; the scoped package readback is authoritative.
  - Source/install module trees both hash cfffb78938a332bf22203595a53362249cb8b1dae2573d32f89b87e285f68819; executable package source hashes 42939f1f3f0de945a4f969392826a0c7ea6ef2418baee4acb7884f3666dc5474.
  - Immutable image sha256:fa118984d55034d1abe09e0b3b6b6ea5d2ceec16b2d24445bd8928269a2865db was content/provenance verified. Fresh task14-f52-smoke-r2 returned one QUALIFIED CUDA candidate from YOLO in 32.80 ms and Grounded-SAM in 151.94 ms, then auto-removed its exact container. The first smoke shell attempt is retained as a pre-container nounset/setup incompatibility with no runtime side effect.
  - Fresh EXP-049 preflight found 24 CPUs, 25.296 GiB MemAvailable, 15272 MiB free GPU, no GPU compute application, related process, or running related container, and all domains 181-183 independently lockable.
open_risks:
  - The production four-point execute has not yet demonstrated Broker model admission after F52.
  - Physical motion and all four point results remain unqualified until EXP-049 passes every frozen gate.
retained: F52 RED/GREEN/adjacent scratch and logs, p67/p68 including invalid harness evidence, provenance, image build/smoke including the pre-container attempt, EXP-049 preflight, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p68 after readback; no deletion authorized
decision: RUN EXP-049 with unchanged four points and physical criteria
```

## EXP-049 — Task 14 F52 two-Worker execute

```yaml
experiment_id: EXP-049
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T22:34:04+08:00
  - status: RUNNING
    at: 2026-09-12T22:34:04+08:00
  - status: INVALID
    at: 2026-09-12T22:36:07+08:00
prior_experiment: EXP-048
hypothesis: F52 will replay the already-loaded model readiness into PerceptionBroker so both Workers can complete perception and proceed under the unchanged physical gates.
prediction: Four unique points finish PASSED with qualification_passed=true, or any failure is bounded, attributable, safely stopped, and physically evidenced.
single_variable: F52 healthy idempotent ready-state replay only. Authorization, Broker checks, reset/gate identity, topology, contact, freshness, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f52
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f52
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 328de1909c6b7ceb19b2d5b6ac9a41e0e7888b69
  executable_source_tree: 42939f1f3f0de945a4f969392826a0c7ea6ef2418baee4acb7884f3666dc5474
  installed_module_tree: cfffb78938a332bf22203595a53362249cb8b1dae2573d32f89b87e285f68819
  image_id: sha256:fa118984d55034d1abe09e0b3b6b6ea5d2ceec16b2d24445bd8928269a2865db
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp049.json; sha256 98f02b2ec8ebfd9700a6e913a2ea3f7534456ec4bc4dc7aebb5e87d6c89c5fea
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-small-20260912-v1-f52 --worker-count 2 --max-points-per-worker 2 --evidence-root /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f52 --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
acceptance: The complete frozen Task 14 live-small gate; any diagnostic failure remains INVALID and non-qualifying.
result: >-
  Command exited 1 after 0.36 seconds with PROVENANCE_CONSOLE_MISSING. The complete overlay makes
  ros2 run locate the package libexec, but does not add that independent verified wrapper to PATH
  for the fail-closed provenance verifier. This is the same already-documented pre-admission
  environment omission as EXP-024. No batch root, Worker, Broker container, MuJoCo log, lease, RGB,
  or physical action was created.
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 99c39672bf29d69af01c4f046a0639a05b3a0be6f0bd7a83577bd768858e1b8b
command_time_sha256: ddef1903ee18db15fb90124ecf56469fba4ca3bc38a385a90dd1882811a56bd4
post_cleanup_sha256: fe64270e36f11f9531df14cae3470e19548c0535c3f28aaf37adc88fbf21494b
conclusion: INVALID pre-admission harness environment; repeat with only the verified worktree libexec prepended to PATH.
retained: EXP-049 command and no-side-effect audit, plus all prior evidence
archived: none
deletion_candidates: none from this pre-admission attempt
```

```yaml
checkpoint_id: CP-038
last_valid_experiment: EXP-022
current_hypothesis: Adding only the verified worktree so101_demo_py libexec to PATH will satisfy the already-reviewed provenance boundary and allow the unchanged F52 execute to run.
working_tree_status: ledger-only EXP-049 result and EXP-050 preregistration after clean executable source 328de1909c6b7ceb19b2d5b6ac9a41e0e7888b69
owned_processes: NONE
confirmed_conclusions:
  - EXP-049 stopped at PROVENANCE_CONSOLE_MISSING before creating its batch root or any runtime side effect.
  - Independent readback resolves so101_parallel_batch exactly to /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch when only that directory is prepended to PATH.
  - Final audit found the EXP-049 root absent, MuJoCo log absent, no related process or container, and all domains 181-183 lockable.
  - Fresh EXP-050 preflight found 24 CPUs, 25.371 GiB MemAvailable, 15272 MiB free GPU, no GPU compute application, related process, or related container, exact verified console resolution, and all domains lockable.
ruling: EXP-050 changes only the command environment by prepending the already-qualified worktree libexec to PATH. F52 source/image, complete overlay, points, configuration, models, N=2, K=2, timeouts, and physical criteria remain unchanged.
retained: complete EXP-049 no-side-effect evidence, EXP-050 preflight, F52 qualification, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p68 after readback; no deletion authorized
decision: RUN EXP-050 under the verified libexec PATH
```

## EXP-050 — Task 14 verified-libexec F52 two-Worker execute

```yaml
experiment_id: EXP-050
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T22:36:27+08:00
  - status: RUNNING
    at: 2026-09-12T22:36:27+08:00
  - status: INVALID
    at: 2026-09-12T22:41:50+08:00
prior_experiment: EXP-049
hypothesis: The verified libexec PATH closes the pre-admission provenance boundary and F52 admits both loaded models into the production Broker.
prediction: Four unique points finish PASSED with qualification_passed=true, or any runtime failure is bounded, attributable, safely stopped, and physically evidenced.
single_variable: PATH prepends only /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py. All executable and behavioral inputs remain those of EXP-049.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f52b
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f52b
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 328de1909c6b7ceb19b2d5b6ac9a41e0e7888b69
  executable_source_tree: 42939f1f3f0de945a4f969392826a0c7ea6ef2418baee4acb7884f3666dc5474
  installed_module_tree: cfffb78938a332bf22203595a53362249cb8b1dae2573d32f89b87e285f68819
  image_id: sha256:fa118984d55034d1abe09e0b3b6b6ea5d2ceec16b2d24445bd8928269a2865db
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp050.json; sha256 3fb24a8ddf8b257166631db4fca349e19663d13d1ecbeb3bde69ac0ec3d7507c
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  PATH=/data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py:$PATH; source install/setup.zsh; ros2 run so101_demo_py so101_parallel_batch with the unchanged EXP-049 arguments, batch parallel-small-20260912-v1-f52b, and root live-small-f52b.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic failure remains INVALID and non-qualifying.
result: >-
  Command exited 1 after 100.15 seconds. F52 closed BROKER_NOT_READY: both Workers passed
  exact reset/gate/ATTEMPT_STARTED and perception, Broker remained healthy, and both accepted
  lease-bound poses. Worker-02 completed the entire physical workflow for cup_test_forward_5cm,
  wrote the 19-transition dynamic manifest, and sealed PASSED/OK. Worker-01's dynamic consumer
  received the accepted task_start pose stamped 3.549999999 s before its newly-created use_sim_time
  clock had caught up, rejected it as CUP_POSE_STALE: source stamp is too far in the future, then
  timed out with no second publication. The Worker conservatively sealed INDETERMINATE with
  DYNAMIC_EXECUTION_RECEIPT_MISSING and physical_action_proven_absent=false; subsequent recovery
  motion occurred. The other two points were never leased and qualification remained false.
visual_observation: >-
  All four immutable 640x480 RGB files were inspected at original resolution. Both initial frames
  match their expected distinct point positions with canonical initial arm and no robot-object
  contact. Worker-02 terminal shows the cup upright at the marked support region and the arm
  retreated, consistent with its PASS. Worker-01 terminal shows the work surface without a visible
  cup and is not acceptable physical evidence; this agrees with the INDETERMINATE result and is not
  counted as a behavior pass.
visual_sha256:
  task_start_initial: 218b60a7787d46a0fa511e1c93f33d593767b7095256c54e145ce009f63d3566
  task_start_terminal: ab5e97ab73ea68f62ea6a9c091018fd0dfa20c4925b68b67fd59d49d4491f28f
  cup_test_forward_5cm_initial: de0090ccb960d7f6c7d855b6c33c4c3ceacc3eaf3f640e04e455c25a977f9e89
  cup_test_forward_5cm_terminal: ea24450d64be560b809b7327a3977ca092e28b5aaadde0f7ee170e02275cdb3e
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: ec4ab1fd636499a68c72d041fbe00ac7e11d23c7ef0cf4c671871d5cdb2a6382
command_time_sha256: 36de92050e715110ccc4ad67330d188ae9abfcae24178b42c547882508aa5b61
aggregate_sha256: eaa25ba1fad7db2a408282fef81615ef43699ee03fdfcf7869f162361af6bcc8
coordinator_aggregate_sha256: 79ea9859780e4a426cc12cdc375d865d9420ec153a992126837565a565425519
worker_01_result_sha256: 2dcaaec506313a019d7b38b244d668244161dfb17d45f9b0557184687dc0beba
worker_02_result_sha256: 034211da0c7805e9ae6f901b32ca91f421315961f62653357afa57882e676a5e
mujoco_log_sha256: 8163a0e8ba57125cdb6ade885ee3f1eea91f8d6afd064e2d74126be8eaa58ab7
cleanup: >-
  Exact CID d76ab5e8f911c143b8ca4bdb4f47e8257362af707fc5a6604184e6294fca2dcd
  was verified against the immutable F52 image, exact batch/generation labels, and registered
  mounts, then stopped. The first immediate removal observation raced Docker --rm; the next bounded
  readback proved it removed. Final audit found no related process, container, or GPU compute task
  and all domains 181-183 lockable. The MuJoCo log was moved without deletion.
post_cleanup_sha256: d53773c1269513e7d4a8e3096e6e65b5847e990d3c05a177cae57fb8198f004c
conclusion: INVALID mixed physical result; one PASSED and one INDETERMINATE. Synchronize the one-shot accepted pose publication to the source simulation timestamp, retain the consumer freshness gate unchanged, then fully requalify.
retained: complete EXP-050 batch/reports, all four visually inspected RGB files, dynamic PASS manifest, INDETERMINATE evidence, moved MuJoCo log, cleanup evidence, and all prior evidence
archived: none
deletion_candidates: no new scratch; no deletion authorized
```

```yaml
checkpoint_id: CP-039
last_valid_experiment: EXP-022
current_hypothesis: Waiting on the Worker's isolated use_sim_time publisher node until its ROS clock reaches the already-admitted pose source stamp will prevent a startup-only false future rejection without weakening the consumer's freshness/skew contract.
working_tree_status: ledger-only EXP-050 result and F53 ruling after clean executable source 328de1909c6b7ceb19b2d5b6ac9a41e0e7888b69
owned_processes: NONE
confirmed_conclusions:
  - Both Workers completed F52 Broker admission; Worker-02 completed all 19 dynamic transitions and sealed PASSED.
  - Worker-01's accepted source stamp was 3.549999999 s. Its new dynamic consumer printed CUP_POSE_STALE: source stamp is too far in the future, then timed out because publication is intentionally one-shot.
  - ParallelRosRuntimePorts.publish_pose currently creates a system-clock node and publishes immediately after subscriber discovery; it does not observe the Worker's simulation clock. The consumer correctly uses use_sim_time and enforces the frozen 0.05 s future-skew limit.
  - A publisher-side use_sim_time wait can prove the same domain clock has reached the accepted source stamp before the existing one-shot publication, keeping every consumer validation unchanged.
  - Worker-01 remained conservatively INDETERMINATE and its unacceptable terminal frame was not counted; exact cleanup completed.
open_risks:
  - The publisher clock synchronization path needs bounded timeout and regression coverage proving no early publication.
  - Full four-point physical qualification remains pending.
ruling: F53 may create the isolated pose publisher node with use_sim_time=true and, within the existing two-second publication bound, spin until its ROS clock is at least admitted.source_stamp_ns before publishing. Timeout must return false, the pose timestamp and one-shot semantics remain unchanged, and no future-skew/freshness threshold may be relaxed. Formal RED/GREEN must prove delayed publication, exact node clock configuration, bounded timeout, and unchanged message contents.
retained: complete EXP-050 evidence, F52 qualification, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p68 after readback; no deletion authorized
decision: IMPLEMENT F53 SOURCE-CLOCK-SYNCHRONIZED POSE PUBLICATION WITH FORMAL RED/GREEN
```

```yaml
checkpoint_id: CP-040
last_valid_experiment: EXP-022
current_hypothesis: F53's source-clock-synchronized one-shot publication will preserve the frozen freshness checks while allowing every newly created use_sim_time consumer to receive its admitted pose.
working_tree_status: clean executable source at 1842d241ec7c639f515f7ece26866f7a0bc5a44c; ledger-only EXP-051 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - Formal RED pytest-HOjSaIn6 failed both new synchronization cases before implementation; focused GREEN pytest-t1sGOxWp passed both after implementation.
  - The valid adjacent gate pytest-Ym2RAJqx passed 73 tests under the complete worktree overlay.
  - p69 build passed in 1.59 seconds; p70 full package test passed 2784 tests with zero errors, failures, or skips in 84.61 seconds.
  - Installed source and build module-tree hashes are both d5e8337bb99af529f71d196988a244001cf16a1ab140dc536f9ae1401945ce22; the complete package source hash is ce7acbe6d0de62e1c40685f7e36ff6cd29bd1c9c5a3a7250a8eaae20ea65df74.
  - Immutable F53 image sha256:8e69f3c804326867c170aed5472411afbabdbeb6b2f6e6af98255b04da7351fb was read back with the same complete source hash.
  - F53 smoke ran both models on CUDA: YOLO and Grounded-SAM each returned QUALIFIED; the exact --rm container disappeared and no GPU compute task remained.
  - Fresh EXP-051 preflight found 24 CPUs, 25.195 GiB MemAvailable, 15272 MiB free GPU, exact verified console resolution, no related process/container/GPU task, and domains 181-183 independently lockable.
open_risks:
  - Four-point physical qualification has not yet been demonstrated with F53.
ruling: Run one new two-Worker four-point gate with only F53 source/image changed from EXP-050. Keep the verified libexec PATH, full overlay, configuration, points, N=2, K=2, models, thresholds, and physical criteria frozen.
retained: all F53 RED/GREEN/adjacent/build/full-test/provenance/image/smoke/preflight evidence, invalid harness attempts, and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p70 after readback; no deletion authorized
decision: RUN EXP-051
```

## EXP-051 — Task 14 source-clock-synchronized F53 two-Worker execute

```yaml
experiment_id: EXP-051
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T22:53:48+08:00
  - status: RUNNING
    at: 2026-09-12T22:53:48+08:00
  - status: INVALID
    at: 2026-09-12T23:01:51+08:00
prior_experiment: EXP-050
hypothesis: F53 will wait for each isolated publisher's simulation clock to reach the admitted source stamp, preventing the startup-only future-stamp rejection while retaining exact one-shot and consumer freshness semantics.
prediction: Four unique points finish PASSED with qualification_passed=true, or any failure is bounded, attributable, safely stopped, and physically evidenced.
single_variable: F53 source-clock-synchronized pose publication only. Verified libexec PATH, full overlay, Broker checks, reset/gate identity, topology, contact, freshness thresholds, selection, config, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f53
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f53
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 1842d241ec7c639f515f7ece26866f7a0bc5a44c
  executable_source_tree: ce7acbe6d0de62e1c40685f7e36ff6cd29bd1c9c5a3a7250a8eaae20ea65df74
  installed_module_tree: d5e8337bb99af529f71d196988a244001cf16a1ab140dc536f9ae1401945ce22
  image_id: sha256:8e69f3c804326867c170aed5472411afbabdbeb6b2f6e6af98255b04da7351fb
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp051.json; sha256 a2c281fe3ae1c39a457fe16184fb0945dec112ad30fd1f938b428e984a4461b2
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  PATH=/data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py:$PATH; source install/setup.zsh; ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-small-20260912-v1-f53 --worker-count 2 --max-points-per-worker 2 --evidence-root /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f53 --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
acceptance: The complete frozen Task 14 live-small gate; any diagnostic failure remains INVALID and non-qualifying.
result: >-
  Command exited 1 after 114.51 seconds. F53 closed the source-clock race: Worker-01
  cup_test_forward_5cm and Worker-02 task_start each completed the 19-transition dynamic
  execution and sealed PASSED/OK. Both Workers then entered mandatory post-point recovery,
  started a replacement physical stack, and produced motion_stack_ready ready=true, but each
  recovery receipt recorded succeeded=false. Both slots were therefore correctly quarantined;
  sample_05_near_center and sample_14_far_right remained UNRUN and the coordinator stopped with
  CAPACITY_EXHAUSTED. The point results remain PASSED, but batch cleanup and qualification are false.
visual_observation: >-
  All four immutable 640x480 RGB files were inspected at original resolution. Both initial frames
  show the expected distinct cup positions with canonical initial arm and no contact. Both terminal
  frames show the cup upright inside the target ring with the arm retreated, consistent with the two
  sealed PASSED results. No visual evidence exists for the two unrun points.
visual_sha256:
  cup_test_forward_5cm_initial: 6184c514feb5dd77da3c8cac67d81810330891dc2de61756a081a2249ef9c281
  cup_test_forward_5cm_terminal: c64e23fba2b041ca3e60353eec83c7d2de02e609d5bf9167f4d5ed593082ddb5
  task_start_initial: b2870627e9c2fe521bb8e8204c323dc9e10e7aed8e9919ffaba7bb28946ba05f
  task_start_terminal: 3e5d6e88fbd01470f55d1113c165c0b827e70222edc17aa055399ee9668ff467
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 224f2973bfea9d0d5fc1ece63770b412f403d2c6134dc2ca0c25a58c7f7317ea
command_time_sha256: a122208c6019edf8fb6f5c7e20cff1fc22e73d88006cbb53e5a02280f56912bd
aggregate_sha256: 52526f8693432b7e631b363b36ea18725eeba689895f3337dadcc13df2384051
coordinator_aggregate_sha256: 5195c78922998f49558b7e9a891dfe09a66d08439baedcf9dee4bdd57ce4f43f
worker_01_result_sha256: 93a9612d09eece6442d347c532b7b20b28485f42d7d50427a76abb5af96a4511
worker_02_result_sha256: 1771b4ac42a322fc8291710868e048e6f5cf5286d9808ecab788da52e7ab0e48
mujoco_log_sha256: 91914ae4aa11da10c1ecdf8fa5324bbae2e9c4039a0eb0a0a0c140c25a741704
cleanup: >-
  Exact CID fa1e2911b7c31edb367ad9bfbc85a97faa93cbc927be7bbdb7cf8fea03c85429
  was verified against the immutable F53 image, exact batch/generation labels, and registered
  mounts, then stopped and removed. Final audit found no related process, container, or GPU task;
  domains 181-183 were independently lockable and the MuJoCo log was moved without deletion.
post_cleanup_sha256: 880fcee1b7f6f5bfbab2a88e18bc5ec4eeaa8f2ca3d3fdd47561acc90482aa1e
conclusion: INVALID recovery-gate false-negative after two valid physical PASSED results. Add bounded per-gate recovery diagnostics before changing any gate semantics.
retained: complete EXP-051 batch/reports, four visually inspected RGB files, both dynamic manifests and PASSED seals, both failed recovery receipts, moved MuJoCo log, cleanup evidence, and all prior evidence
archived: none
deletion_candidates: no new scratch; no deletion authorized
```

```yaml
checkpoint_id: CP-041
last_valid_experiment: EXP-022
current_hypothesis: One of the existing generation fence, cancellation acknowledgement, independent no-goal confirmation, old-stack shutdown, or replacement-ready gates is returning a false negative after a physically successful point; the current boolean-only receipt cannot distinguish them.
working_tree_status: ledger-only EXP-051 result after clean executable source 1842d241ec7c639f515f7ece26866f7a0bc5a44c
owned_processes: NONE
confirmed_conclusions:
  - Both F53 pose publications and physical executions passed, so the prior source-clock defect is closed.
  - Each Worker started a replacement stack and motion_stack_ready reported ready=true before quarantine, proving recovery progressed beyond old-stack shutdown and replacement startup.
  - Each immutable recovery receipt records only succeeded=false; it does not identify the failing sub-gate.
  - Exact cleanup completed and no unrun point was treated as qualified.
ruling: Add one bounded, deterministic RECOVERY_GATES diagnostic containing only the five existing boolean sub-gates before the immutable receipt is written. Do not relax, skip, reorder, or reinterpret any recovery gate. Prove the diagnostic with formal RED/GREEN, then rebuild and repeat the same four-point gate under a new batch ID.
retained: complete EXP-051 and all prior evidence
archived: none
deletion_candidates: direct pytest scratch and p51-p70 after readback; no deletion authorized
decision: IMPLEMENT F54 RECOVERY-GATE DIAGNOSTIC
```

```yaml
checkpoint_id: CP-042
last_valid_experiment: EXP-022
current_hypothesis: F54's bounded RECOVERY_GATES line will identify the existing false-negative sub-gate without changing physical or recovery behavior.
working_tree_status: clean executable source at fa8d1d810c69495280c0ed6810b10bb9c05cc933; ledger-only EXP-052 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - Formal RED pytest-XJOkTMY8 failed because the gate diagnostic was absent; focused GREEN pytest-She3hQtZ passed after adding it.
  - Adjacent pytest-KFDvwL7g passed 119 Worker/ROS runtime tests.
  - p71 build passed in 1.42 seconds; p72 passed 2785 tests with zero errors, failures, or skips in 83.97 seconds.
  - Installed source/build module tree hash is 5ac2888fdecc6de75ea771f54cc955f7845709c79037bdf3bfb8ce79b86c2ccc and complete source hash is 06b7de0b38c26fe620ef98e68d4e6354d838ddd99e73b0e81629c86f3d1927e0.
  - Immutable F54 image sha256:351f01a6ff5609508a9b06c75a6479b673b32aaf0b1665192457dac168ca7fcd passed exact provenance readback and both CUDA model smoke paths returned QUALIFIED.
  - Fresh EXP-052 preflight found 24 CPUs, 25.166 GiB MemAvailable, 15269 MiB free GPU, no related process/container/GPU task, exact console resolution, and all domains lockable.
ruling: Repeat the unchanged two-Worker four-point execute gate solely to collect the new diagnostic. Do not treat the two already-passing physical points as qualification if recovery or remaining points fail.
retained: F54 RED/GREEN/adjacent/p71/p72/provenance/image/smoke/preflight evidence and all prior evidence
archived: none
deletion_candidates: pytest-XJOkTMY8, pytest-She3hQtZ, pytest-KFDvwL7g, p71, and p72 after readback; no deletion authorized
decision: RUN EXP-052
```

## EXP-052 — Task 14 F54 recovery-gate diagnostic execute

```yaml
experiment_id: EXP-052
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T23:08:10+08:00
  - status: RUNNING
    at: 2026-09-12T23:08:10+08:00
  - status: INVALID
    at: 2026-09-12T23:12:23+08:00
prior_experiment: EXP-051
hypothesis: The unchanged recovery outcome plus F54 diagnostic will identify exactly which of fenced/stopped/confirmed/recovered/ready is false after a passing point.
prediction: Either four points pass, or both recovery paths emit bounded deterministic gate diagnostics that permit one evidence-backed fix.
single_variable: One RECOVERY_GATES stdout JSON line before each recovery receipt. No gate, order, threshold, physical behavior, models, N=2, K=2, points, or timeout changed.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f54
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f54
success_criteria: Complete diagnostic for each recovery; physical qualification still requires exit 0, POINTS_COMPLETE, four PASSED points, qualification_passed=true, complete cleanup and visual evidence.
provenance:
  executable_source_commit: fa8d1d810c69495280c0ed6810b10bb9c05cc933
  executable_source_tree: 06b7de0b38c26fe620ef98e68d4e6354d838ddd99e73b0e81629c86f3d1927e0
  installed_module_tree: 5ac2888fdecc6de75ea771f54cc955f7845709c79037bdf3bfb8ce79b86c2ccc
  image_id: sha256:351f01a6ff5609508a9b06c75a6479b673b32aaf0b1665192457dac168ca7fcd
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
preflight: reports/preflight-exp052.json; sha256 8d594f6df84d1af4ef230c9c41b0056bac50b86d08b51cadc51a1e08f4edadce
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact EXP-051 command under the verified libexec PATH and full overlay, with batch parallel-small-20260912-v1-f54 and root live-small-f54.
acceptance: The complete frozen Task 14 live-small gate plus exact bounded RECOVERY_GATES diagnostic readback.
result: >-
  Command exited 1 after 116.19 seconds and produced the required exact diagnosis. Worker-01
  completed cup_test_forward_5cm and sealed PASSED. Worker-02 sealed task_start INVALID before
  action because its exact TF lookup transiently reported that world did not exist. Both post-point
  recovery paths emitted fenced=true, recovered=true, ready=true, stopped=false, confirmed=false.
  This isolates the repeatable recovery false negative to both action-status readers, not Broker
  fencing, old-stack shutdown, resource replacement, or replacement readiness. The two readers use
  volatile depth=10 subscriptions, unlike the already-correct initial gate, so they cannot receive
  the action servers' transient-local retained terminal status when no new status transition occurs.
visual_observation: >-
  The three available immutable 640x480 RGB files were inspected at original resolution.
  cup_test_forward_5cm initial is correct and its terminal shows an upright cup in the target ring
  with the arm retreated, consistent with PASSED. task_start has only a correct no-contact initial
  frame because the exact TF boundary failed before action; it is not counted as a behavior result.
visual_sha256:
  cup_test_forward_5cm_initial: fad007b56ded2b87722b56a2c926d8e16612a09d9daeabdca4be3481df382f3d
  cup_test_forward_5cm_terminal: 5e759d3aa989ccd5c63a4bd681d40ed3a0b14bf2d3ae7119081e7209a017ff17
  task_start_initial: 1c720010f645481f85786c9b8e63615ab96ad2ae2818f810f87545cb0d51f343
recovery_diagnostics:
  worker_01: '{"confirmed":false,"fenced":true,"kind":"RECOVERY_GATES","ready":true,"recovered":true,"stopped":false,"worker_generation":1,"worker_id":"worker-01"}'
  worker_02: '{"confirmed":false,"fenced":true,"kind":"RECOVERY_GATES","ready":true,"recovered":true,"stopped":false,"worker_generation":1,"worker_id":"worker-02"}'
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: abf3f12889a710c943901ef348826874066891df49420a155ddcac269056edb3
command_time_sha256: ec6e56129fb159a4d16f37e4073e6ed4ca50cbddbdd42fbd169088c416c33b47
aggregate_sha256: 33d3349c8241bda9c934ca7512775e21fab470f6274cd7a28ca129e388879231
worker_01_result_sha256: 93a9612d09eece6442d347c532b7b20b28485f42d7d50427a76abb5af96a4511
worker_02_result_sha256: 7a1c38a8c520d08c6ea55956f5a936ee4f2505cf914ee8fda553fa9b41bbcc8a
mujoco_log_sha256: e2e16068681dcc9b80ee5394d4bbf9f40297b3241f9b2d1148785d5898177b86
cleanup: >-
  Exact CID ce428827a0f5d1aab86c8e7ec8f06a368f6337fec40e52cfaedb2f3952f4005e
  was verified against the F54 image and batch/generation/mount identity, then stopped and removed.
  Final audit found no related process, container, or GPU task, all domains lockable, and moved the
  MuJoCo log without deletion.
post_cleanup_sha256: 0e2efb033cff290de954acc9c21ca6915d733222b55224e2ebe92d028528d21f
conclusion: INVALID diagnostic run; use the ROS action status transient-local QoS for both recovery status readers and retain all existing cancellation/confirmation gates.
retained: complete EXP-052 batch/reports, three inspected RGB files, diagnostic lines, recovery receipts, moved MuJoCo log, cleanup evidence, and all prior evidence
archived: none
deletion_candidates: no new scratch; no deletion authorized
```

```yaml
checkpoint_id: CP-043
last_valid_experiment: EXP-022
current_hypothesis: Using qos_profile_action_status_default for both recovery status subscriptions will deliver retained terminal action states and make the unchanged cancel-plus-independent-confirm gates pass without weakening them.
working_tree_status: clean executable source at 02c21600d after formal QoS RED/GREEN; ledger-only EXP-052 result pending commit
owned_processes: NONE
confirmed_conclusions:
  - EXP-052 proved stopped=false and confirmed=false for both slots while fenced/recovered/ready were true.
  - Both failing readers passed integer depth 10; the initial point gate already uses qos_profile_action_status_default for the same three action status topics.
  - Formal RED proved both readers supplied [10,10,10,10,10,10]; focused GREEN proved all six now use qos_profile_action_status_default and both cancellation/confirmation paths retain their exact success conditions.
  - Adjacent Worker/ROS gate passed 120 tests.
ruling: F55 changes only the two action-status subscription QoS arguments to the ROS action default transient-local profile. Cancellation requests, active-state set, three exact topics, independent confirmation, timeouts, and every recovery admission gate remain unchanged.
retained: EXP-052 and F55 RED/GREEN/adjacent evidence plus all prior evidence
archived: none
deletion_candidates: new direct pytest scratch after readback; no deletion authorized
decision: BUILD AND FULLY QUALIFY F55 BEFORE A NEW FOUR-POINT EXECUTE
```

```yaml
checkpoint_id: CP-044
last_valid_experiment: EXP-022
current_hypothesis: F55's transient-local action status readers will let both successful and conservative-invalid point paths complete mandatory recovery and continue dynamic global queue claiming.
working_tree_status: clean executable source at 02c21600d with ledger head cde714fe2; EXP-053 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - F55 formal RED pytest-FJiVpktj captured six integer depth values; focused GREEN pytest-pleJ1RmJ proved six qos_profile_action_status_default subscriptions.
  - Adjacent pytest-HuYPBPZj passed 120 Worker/ROS runtime tests.
  - p73 is retained invalid because the command accidentally named unknown package Notebook even though colcon ignored it; p74 exact so101_demo_py build passed in 1.39 seconds.
  - p75 full package test passed 2786 tests with zero errors, failures, or skips in 83.58 seconds.
  - Installed source/build module tree hash is 8550d93541e9de491c6b428ae313fe0c2953da2593f4923cd3fe71c40d407277 and complete source hash is dbe01edb7d6be8b64ddd8f4acf4a6904b0d1ae6f69da49f8d9d25405e2bf2538.
  - Immutable F55 image sha256:77fc479d565429929d749e8f34594999c929a4a3d4937dbdebc480542b2a2c87 passed provenance readback and both CUDA models returned QUALIFIED in smoke.
  - Fresh EXP-053 preflight found 24 CPUs, 25.086 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, exact console resolution, and domains 181-183 lockable.
ruling: Run a new four-point two-Worker execute gate with only F55 QoS changed from F54; retain the recovery diagnostic for positive readback.
retained: F55 tests, p73 invalid harness, p74/p75, provenance/image/smoke/preflight, and all prior evidence
archived: none
deletion_candidates: pytest-FJiVpktj, pytest-pleJ1RmJ, pytest-HuYPBPZj, p73, p74, and p75 after readback; no deletion authorized
decision: RUN EXP-053
```

## EXP-053 — Task 14 transient-local recovery F55 two-Worker execute

```yaml
experiment_id: EXP-053
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T23:19:22+08:00
  - status: RUNNING
    at: 2026-09-12T23:19:22+08:00
  - status: INVALID
    at: 2026-09-12T23:23:58+08:00
prior_experiment: EXP-052
hypothesis: Retained action terminal statuses will satisfy both cancel and independent no-goal recovery checks, re-admit each slot at generation 2, and allow all four points to complete.
prediction: Four unique points finish PASSED with qualification_passed=true and both Workers emit all-true recovery gates after each point.
single_variable: qos_profile_action_status_default replaces depth=10 for the same six recovery status subscriptions. All other source, configuration, models, points, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f55
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f55
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all-true recovery gates, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 02c21600da0367f4ef7b79c54387bedcb5282123
  executable_source_tree: dbe01edb7d6be8b64ddd8f4acf4a6904b0d1ae6f69da49f8d9d25405e2bf2538
  installed_module_tree: 8550d93541e9de491c6b428ae313fe0c2953da2593f4923cd3fe71c40d407277
  image_id: sha256:77fc479d565429929d749e8f34594999c929a4a3d4937dbdebc480542b2a2c87
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
preflight: reports/preflight-exp053.json; sha256 9357f1078646c7cde9316f00c62ffc68a7c3c631c7d782f64a12db7a4f5e6383
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260912-v1-f55 and root live-small-f55.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: >-
  Command exited 1 after 124.22 seconds. Worker-02 completed cup_test_forward_5cm and sealed
  PASSED. Worker-01 sealed task_start INVALID at point_initial_gate because its exact graph snapshot
  transiently missed robot_state_publisher and rejected an inconsistent node set. Both mandatory
  recoveries again reported stopped=false and confirmed=false while fenced, recovered, and ready
  were true. The QoS correction therefore was necessary but not sufficient. Source inspection and
  the repeated ignored SingleThreadedExecutor.__del__ _sigint_gc exceptions show both helpers call
  rclpy.spin_once(node) without an executor even though _open_isolated_ros_node created the node on
  a private Context; rclpy then constructs/uses the default-context global executor instead of an
  executor bound to the private node context, and both recovery calls fail closed.
visual_observation: >-
  The two available 640x480 RGB files were inspected at original resolution. The
  cup_test_forward_5cm initial frame has the expected cup position and no contact; its terminal
  frame shows the cup upright in the target ring with the arm retreated, consistent with PASSED.
  task_start failed before RGB capture and has no physical behavior evidence.
visual_sha256:
  cup_test_forward_5cm_initial: 26ec41b1c975a34a931f22ba01067f06f7ed87e04c67699653b15849948177c3
  cup_test_forward_5cm_terminal: ade1483c89b7ee12f0db990baa0770e91617dc01e7d3fda147115d21dbcf27bf
recovery_diagnostics:
  worker_01: '{"confirmed":false,"fenced":true,"kind":"RECOVERY_GATES","ready":true,"recovered":true,"stopped":false,"worker_generation":1,"worker_id":"worker-01"}'
  worker_02: '{"confirmed":false,"fenced":true,"kind":"RECOVERY_GATES","ready":true,"recovered":true,"stopped":false,"worker_generation":1,"worker_id":"worker-02"}'
command_exit_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
command_log_sha256: 0f3577eab85c73bf634dbf5bc0f4389499c314843890574c2e03e91fe9fcbb42
command_time_sha256: a2fe8cc8001d46bbd775c2d7f1681e462403f70bf73ef73294321c7641768b61
aggregate_sha256: 33d3349c8241bda9c934ca7512775e21fab470f6274cd7a28ca129e388879231
worker_01_result_sha256: 66b39434abdfe320e36391f85e7bebebe9b4207ea4c80efabf75b3fc763fe28b
worker_02_result_sha256: 034211da0c7805e9ae6f901b32ca91f421315961f62653357afa57882e676a5e
mujoco_log_sha256: ea168f77550e9d2c7001139f2776539acc70afef1e0feebe88d5c1cccf494d0a
cleanup: >-
  Exact CID 7dc04dcb8a12386b4a14c0fbb24b162e446604930dacdcdde7b64f647e6b0217
  was verified against F55 and its batch/generation/mount identity, then stopped and removed.
  Final audit found no related process, container, or GPU task, all domains lockable, and the
  MuJoCo log moved without deletion.
post_cleanup_sha256: 92323f4d0fad526ce0afe5c5ecfcf885043930e4026505eb10d3ad4c17fe1db4
conclusion: INVALID; bind a dedicated executor to each isolated ROS Context and spin both recovery readers only through that executor.
retained: complete EXP-053 batch/reports, two inspected RGB files, recovery diagnostics/receipts, moved MuJoCo log, cleanup evidence, and all prior evidence
archived: none
deletion_candidates: no new scratch; no deletion authorized
```

```yaml
checkpoint_id: CP-045
last_valid_experiment: EXP-022
current_hypothesis: A SingleThreadedExecutor constructed with the same private Context as each recovery node will receive the retained action status callbacks and eliminate the default-context failure while preserving isolation.
working_tree_status: ledger-only EXP-053 result after executable source 02c21600da0367f4ef7b79c54387bedcb5282123
owned_processes: NONE
confirmed_conclusions:
  - Transient-local QoS alone did not change the live recovery outcome; both readers still failed together.
  - rclpy.spin_once without an explicit executor always uses get_global_executor(), whose executor is tied to get_default_context().
  - Both nodes are intentionally created with explicit private Context objects, so passing them to the implicit global executor violates the isolation model.
  - The live logs repeatedly show partially constructed default SingleThreadedExecutor destructor errors with missing _sigint_gc exactly at these swallowed recovery exceptions.
ruling: F56 may extend _IsolatedRosNode to own a SingleThreadedExecutor(context=the same private context), add its node exactly once, expose spin_once(timeout_sec), and remove/shutdown that executor during close before shutting the context. The two helpers must use owner.spin_once; QoS, topics, requests, status rules, and timeouts stay unchanged.
retained: EXP-053 evidence and all prior evidence
archived: none
deletion_candidates: existing scratch only; no deletion authorized
decision: IMPLEMENT F56 PRIVATE-CONTEXT EXECUTOR WITH FORMAL RED/GREEN
```

```yaml
checkpoint_id: CP-046
last_valid_experiment: EXP-022
current_hypothesis: F56's private-context executors will let the already-correct transient-local recovery subscriptions execute callbacks and re-admit both slots.
working_tree_status: clean executable source at dd3f2071476ef4aacc1acd77e92322980391cc10; ledger-only EXP-054 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - Formal RED pytest-VxSwDw2v failed because _IsolatedRosNode had no context-bound executor or spin_once.
  - Focused GREEN pytest-bwavH9EL passed both private-executor and recovery-QoS cases; adjacent pytest-U2jLrmTx passed 120 tests.
  - p76 exact build passed in 1.37 seconds; p77 full package test passed 2786 tests with zero errors, failures, or skips in 83.77 seconds.
  - Installed source/build module tree hash is 84d2a6b3024998af08066773b6917976f9deff7aee83eb2b531de49725e73150 and complete source hash is 147e7b947e9e4ed3ce063eda7093f9d8a7cdc8ed8d50de051d8b74310ceb1ba5.
  - Immutable F56 image sha256:f18aca1428823046d5eec9cd088bb16400a9f999cec742a9c6d0c80c22d3cc37 passed provenance readback and both CUDA smoke paths returned QUALIFIED.
  - Fresh EXP-054 preflight found 24 CPUs, 25.106 GiB MemAvailable, 15272 MiB free GPU, exact console resolution, no related process/container/GPU task, and all domains lockable.
ruling: Run the unchanged four-point gate with only the F56 private executor behavior changed. Require all-true recovery diagnostics before counting dynamic continuation.
retained: F56 RED/GREEN/adjacent/p76/p77/provenance/image/smoke/preflight evidence and all prior evidence
archived: none
deletion_candidates: pytest-VxSwDw2v, pytest-bwavH9EL, pytest-U2jLrmTx, p76, and p77 after readback; no deletion authorized
decision: RUN EXP-054
```

## EXP-054 — Task 14 private recovery executor F56 two-Worker execute

```yaml
experiment_id: EXP-054
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-12T23:29:10+08:00
  - status: RUNNING
    at: 2026-09-12T23:29:10+08:00
prior_experiment: EXP-053
hypothesis: Both recovery action-status readers will execute on their private context, report stopped=true and confirmed=true, re-admit generation 2, and finish all four points.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, and every recovery diagnostic is all true.
single_variable: Dedicated same-context executor ownership/spinning for the two isolated recovery ROS nodes. All QoS, topics, requests, status rules, source, config, points, models, N=2, K=2, timeouts, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f56
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f56
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all-true recovery gates, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: dd3f2071476ef4aacc1acd77e92322980391cc10
  executable_source_tree: 147e7b947e9e4ed3ce063eda7093f9d8a7cdc8ed8d50de051d8b74310ceb1ba5
  installed_module_tree: 84d2a6b3024998af08066773b6917976f9deff7aee83eb2b531de49725e73150
  image_id: sha256:f18aca1428823046d5eec9cd088bb16400a9f999cec742a9c6d0c80c22d3cc37
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
preflight: reports/preflight-exp054.json; sha256 c58f45500fab40dedbd809cd80d2cc28d5232a6a5ca0b43017b6767dddaac737
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260912-v1-f56 and root live-small-f56.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: INVALID — harness transcription used a nonexistent YOLO path and two mistyped frozen hashes, so the CLI failed closed with YOLO_HASH_MISMATCH in 0.33 seconds before starting ROS, Docker, or physical execution.
retained: preflight, command-054 log/time/exit, post-failure readback, and prior evidence
archived: none
deletion_candidates: none from this experiment yet
```

```yaml
checkpoint_id: CP-047
last_valid_experiment: EXP-022
current_hypothesis: EXP-054 exercised no implementation behavior; the F56 private-context executor hypothesis remains unchanged.
working_tree_status: clean executable source at dd3f2071476ef4aacc1acd77e92322980391cc10; ledger-only EXP-055 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-054 stopped at immutable-input verification in 0.33 seconds with YOLO_HASH_MISMATCH and did not start ROS, Docker, GPU work, or a physical action.
  - Readback recovered the already-qualified exact YOLO path and sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781.
  - Readback recovered the frozen Grounded-SAM manifest sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775.
  - No batch-labelled container or GPU compute application exists after the failed precheck.
ruling: Preserve EXP-054 as invalid harness evidence and repeat the unchanged four-point gate as EXP-055 with the exact previously qualified model path and hashes.
retained: EXP-054 and all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: RUN EXP-055
```

## EXP-055 — Task 14 private recovery executor F56 two-Worker execute, corrected frozen model literals

```yaml
experiment_id: EXP-055
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T23:32:14+08:00
  - status: RUNNING
    at: 2026-09-12T23:32:14+08:00
  - status: INVALID
    at: 2026-09-12T23:37:05+08:00
prior_experiment: EXP-054
hypothesis: Both recovery action-status readers will execute on their private context, report stopped=true and confirmed=true, re-admit generation 2, and finish all four points.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, and every recovery diagnostic is all true.
single_variable: No implementation or experiment variable changed from EXP-054; only the command transcription is corrected to the exact previously qualified YOLO path and frozen YOLO/Grounded-SAM hashes.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f56-r2
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f56-r2
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all-true recovery gates, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: dd3f2071476ef4aacc1acd77e92322980391cc10
  executable_source_tree: 147e7b947e9e4ed3ce063eda7093f9d8a7cdc8ed8d50de051d8b74310ceb1ba5
  installed_module_tree: 84d2a6b3024998af08066773b6917976f9deff7aee83eb2b531de49725e73150
  image_id: sha256:f18aca1428823046d5eec9cd088bb16400a9f999cec742a9c6d0c80c22d3cc37
  yolo_path: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
preflight: Reuse EXP-054 preflight because the failed command created no process/container/domain claim; exact model readback recorded at CP-047.
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260912-v1-f56-r2, root live-small-f56-r2, and the exact qualified model literals above.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: INVALID — exit 1 after 200.49 seconds. task_start and sample_05_near_center physically PASSED with 19 transitions and visually upright centered placement plus retreat. cup_test_forward_5cm was INVALID before action because exact task_camera_frame TF was transiently unavailable; sample_14_far_right remained UNRUN. Worker-02 recovered twice with all five gates true. Worker-01 had physical_action_proven_absent=true but stopped=false and confirmed=false because no action status had ever been published, then was quarantined; terminal reason CAPACITY_EXHAUSTED, execution_complete=false, batch_cleanup_complete=false, qualification_passed=false.
broker_readback: Container dfc4ebd599cf0acbf5ddf24111967f491caf3f0bc5cf631cc76c0d18f0923ebc matched the exact F56 image, source label, batch label, isolated network/IPC, GPU request, and model mounts. It was stopped by exact ID and Docker auto-removed it.
cleanup_readback: No related process, container, GPU compute application, or ROS domain 181-183 claim remained after manual exact-container cleanup.
visual_readback: Five authorized RGB images were inspected at original resolution; both terminal images are visual PASS and the INVALID point has initial evidence only.
retained: complete live-small-f56-r2 tree, command-055 log/time/exit, broker inspect summary, visual report, MuJoCo log, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-048
last_valid_experiment: EXP-022
current_hypothesis: A trusted pre-action absence proof must satisfy the recovery stop/confirmation gates when ROS action servers have never published a status sample; any action-may-have-started path must retain the existing fail-closed observations.
working_tree_status: clean executable source at 7b50d7e25348546cbe667d9a31adcbd1a050d9e6; ledger-only EXP-056 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-055 isolated the false-negative recovery case: the INVALID attempt sealed physical_action_proven_absent=true, while the same run's two post-action Worker-02 recoveries were all true.
  - Formal RED pytest-0el54IO6 failed exactly because recovery ignored the trusted pre-action absence proof. The corrected focused run pytest-V6oQVUzk passed 3 tests and adjacent pytest-H4igAEI6 passed 121 tests.
  - F57 still calls cancel_motion and confirm_no_controller_goal, but only a strict physical_action_proven_absent=true may satisfy missing status observations. The uncertain/action-started comparison remains fail closed.
  - Source commit 7b50d7e25348546cbe667d9a31adcbd1a050d9e6; p78 symlink build passed in 1.59 seconds.
  - p79 and p80 are retained harness failures: p79 used system Pydantic v1 and p80 failed its pre-test dependency assertion. p81 used the verified combined dependency path and passed 2787 tests with zero errors, failures, or skips in 83.81 seconds.
  - Installed/source module tree hash is b96a2d1f3c907caa5d1f68cd8b03f8a72bbc3900cd4f34c8cc2eb05fc09ea732; complete source hash is 911022eb412a4f78f45bb92585bbd453c0efdcaf33939e2e7f46a2c10c94b962; compileall and frozen input hashes passed.
  - F57 image sha256:418148abd88b3551d5cb3cad1f3b3cac36fd8ee7dc372cba98ebbcac9c4985e9 binds the exact source hash. The corrected smoke returned QUALIFIED CUDA for YOLO and Grounded-SAM and left no container or GPU process.
  - Fresh EXP-056 preflight found 24 CPUs, 25.000 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged four-point execute gate with only the F57 pre-action recovery proof behavior changed. A recurrent TF failure remains INVALID but must no longer quarantine a slot if no action was possible.
retained: EXP-055 evidence, F57 RED/GREEN/adjacent/build/package/provenance/image/smoke/preflight evidence, and all prior evidence
archived: none
deletion_candidates: pytest-0el54IO6, pytest-HhTF8blg, pytest-V6oQVUzk, pytest-H4igAEI6, p78, p79, p80, and p81 after readback; no deletion authorized
decision: RUN EXP-056
```

## EXP-056 — Task 14 pre-action recovery proof F57 two-Worker execute

```yaml
experiment_id: EXP-056
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T23:51:23+08:00
  - status: RUNNING
    at: 2026-09-12T23:51:23+08:00
  - status: INVALID
    at: 2026-09-12T23:59:57+08:00
prior_experiment: EXP-055
hypothesis: Both slots remain recoverable through K=2 even if one point fails before any formal action status exists, while any post-action recovery still requires observed cancellation and independent confirmation.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, and every recovery diagnostic is all true.
single_variable: Recovery may use an already-sealed strict physical_action_proven_absent=true fact to satisfy missing action-status samples; all ROS observation paths and every other source/config/model/point/timeout/physical criterion remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f57
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f57
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete recovery receipts, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 7b50d7e25348546cbe667d9a31adcbd1a050d9e6
  executable_source_tree: 911022eb412a4f78f45bb92585bbd453c0efdcaf33939e2e7f46a2c10c94b962
  installed_module_tree: b96a2d1f3c907caa5d1f68cd8b03f8a72bbc3900cd4f34c8cc2eb05fc09ea732
  image_id: sha256:418148abd88b3551d5cb3cad1f3b3cac36fd8ee7dc372cba98ebbcac9c4985e9
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp056.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260912-v1-f57 and root live-small-f57.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: INVALID — exit 1 after 220.06 seconds. cup_test_forward_5cm and sample_05_near_center physically PASSED with complete dynamic receipts and visually upright centered placement plus retreat. task_start became INDETERMINATE because the dynamic consumer rejected the already-audited pose as CUP_POSE_STALE after MuJoCo simulation time advanced more than the frozen 5-second source-age limit during consumer startup; sample_14_far_right remained UNRUN. Worker-01 recovered both post-action points with all gates true. Worker-02 correctly remained quarantined because action might have started and stopped/confirmed were false. Terminal reason CAPACITY_EXHAUSTED, execution_complete=false, batch_cleanup_complete=false, and qualification_passed=false.
broker_readback: Container bfe2e613253b557df82eb1c87bbf50700ba749da229588101d9af2ac8f855364 matched the exact F57 image, source label, batch label, isolated network/IPC, GPU request, and model mounts. It was stopped by exact ID and Docker auto-removed it.
cleanup_readback: No related process, container, GPU compute application, or ROS domain 181-183 claim remained after exact-container cleanup.
visual_readback: Six authorized original-resolution RGB images were inspected; both PASSED terminal images show upright centered placement and retreat, while task_start initial and terminal frames are identical with the cup unmoved and arm reset. Formal status remains INDETERMINATE because action-start absence was not proven.
retained: complete live-small-f57 tree, command-056 log/time/exit, broker inspect summary, visual report, MuJoCo log, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-049
last_valid_experiment: EXP-022
current_hypothesis: Freeze simulation time only while the already-audited pose's dynamic consumer starts and the pose is published, then resume simulation before execution, preserving the frozen 5-second freshness threshold and source stamp.
working_tree_status: clean executable source at e921c313424093761ac86822a36e2e4d453ed2e8; ledger-only EXP-057 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-056 isolated a simulation-clock race: task_start perception and POSE_ACCEPTED completed, then the newly started consumer observed CUP_POSE_STALE after accelerated simulation time advanced beyond the 5-second source-age limit.
  - Formal RED pytest-I9ubO75F proved the runtime lacked pause control. Focused pytest-jnjnEOpT passed 1 test, expanded pytest-TQR0vb7r passed 4 tests, and adjacent pytest-jMNPgO0V passed 78 tests after the correction.
  - F58 pauses physics before consumer startup, waits for readiness and publishes the accepted pose while paused, resumes in a finally block, and only then awaits execution. Pause/resume errors fail closed and execution never proceeds while paused.
  - Source commit e921c313424093761ac86822a36e2e4d453ed2e8; p82 symlink build passed in 1.53 seconds; p83 passed 2789 tests with zero errors, failures, or skips in 84.68 seconds.
  - Installed/source module tree hash is cb87c4b33466636041847e18edd566784f0f2a00e4c58e7bfc0998fb622aabe8; complete source hash is 74cb881b931f16b38ca55a188be65a2a5ccbbbb4d39f493ab36c41722ff7bd71; compileall and frozen input hashes passed.
  - F58 image sha256:0e4733e3077c60ebeea053b3212316f2d36fe3b39fd1977525d92f47ad0baa9c binds the exact source hash. The corrected build completed in 12.26 seconds, and smoke returned QUALIFIED CUDA for YOLO in 33.83 ms and Grounded-SAM in 191.94 ms with no residual container or GPU process. The first build wrapper invocation is retained as an invalid pre-Docker environment-loading attempt.
  - Fresh EXP-057 preflight found 24 CPUs, 24.995 GiB MemAvailable, 15269 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged four-point execute gate with only the F58 simulation-pause window around dynamic consumer startup and audited pose publication changed.
retained: EXP-056 evidence, F58 RED/GREEN/adjacent/build/package/provenance/image/smoke/preflight evidence, and all prior evidence
archived: none
deletion_candidates: pytest-I9ubO75F, pytest-jnjnEOpT, pytest-TQR0vb7r, pytest-jMNPgO0V, p82, and p83 scratch trees after readback; no deletion authorized
decision: RUN EXP-057
```

## EXP-057 — Task 14 pose-freshness pause F58 two-Worker execute

```yaml
experiment_id: EXP-057
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T00:09:03+08:00
  - status: RUNNING
    at: 2026-09-13T00:09:03+08:00
  - status: INVALID
    at: 2026-09-13T00:16:54+08:00
prior_experiment: EXP-056
hypothesis: Holding simulation time fixed during dynamic consumer startup and audited pose publication will preserve exact source freshness, after which both isolated slots recover through K=2 and finish all four points.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, every dynamic execution receipt is complete, and every recovery diagnostic is all true.
single_variable: Physics is paused only around dynamic consumer startup, readiness, and publication of the immutable accepted pose, then resumed before awaiting execution; every source/config/model/point/timeout/freshness/physical criterion remains frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f58
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f58
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete recovery/dynamic receipts, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: e921c313424093761ac86822a36e2e4d453ed2e8
  executable_source_tree: 74cb881b931f16b38ca55a188be65a2a5ccbbbb4d39f493ab36c41722ff7bd71
  installed_module_tree: cb87c4b33466636041847e18edd566784f0f2a00e4c58e7bfc0998fb622aabe8
  image_id: sha256:0e4733e3077c60ebeea053b3212316f2d36fe3b39fd1977525d92f47ad0baa9c
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp057.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f58 and root live-small-f58.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: INVALID — exit 1 after 125.42 seconds. Both initially claimed points became INDETERMINATE before action: execute_expert reported POSE_ACCEPTED_PUBLICATION_FAILED, then each prestarted consumer reported CUP_POSE_TIMEOUT. Pausing physics before constructing the fresh use_sim_time publisher and consumer prevented either node from observing a positive source-era /clock sample, so the publisher refused the immutable positive source stamp. Both Workers were quarantined, the remaining two points stayed UNRUN, execution_complete=false, batch_cleanup_complete=false, and qualification_passed=false.
broker_readback: Container dcd6d4b5f7184137e89bacecd129b192e8859b76952d97844e94fc4a96d68d4e matched the exact F58 image, source label, batch label, isolated network/IPC, GPU request, and model mounts. It was stopped by exact ID and Docker auto-removed it.
cleanup_readback: No related process, container, GPU compute application, or ROS domain 181-183 claim remained after exact-container cleanup.
visual_readback: Two authorized initial 640x480 RGB images were inspected at original resolution; both cups were upright at the configured source anchors outside the red targets, both arms were reset, and no terminal frame existed because no action was authorized.
retained: complete live-small-f58 tree, command-057 log/time/exit, broker inspect summary, visual report, root-cause report, MuJoCo log, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-050
last_valid_experiment: EXP-022
current_hypothesis: Construct and confirm the exact dynamic consumer before the immutable inference snapshot so it has an advancing simulation-clock history; then publish the audited fresh pose without pausing physics.
working_tree_status: clean executable source at 158b99df17a5a28b8da0d2780fdc71e06ff0c2ae; ledger-only EXP-058 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-057 isolated the pause/bootstrap deadlock: a newly constructed use_sim_time publisher and consumer cannot acquire source-era clock history while MuJoCo physics is paused before their construction.
  - Formal RED pytest-AnMJppAb failed because the runtime captured rgb.npy before starting the dynamic consumer. Focused GREEN pytest-vbKZ3oNz passed, the corrected runtime file gate pytest-38cMnRdr passed 50 tests, and the corrected adjacent gate pytest-FGGDyRNZ passed 234 tests. Retained harness failures are pytest-o9uK0l (shell-function invocation), pytest-cLCEq87I (stale expectations), pytest-RHO3gTD8 (test-spy oversight), and pytest-rIdch8Hi (partial overlay dependency order).
  - F59 keys prestarted consumers by lease, requires readiness before the exact inference snapshot, reuses only that exact child for execute_expert, and removes the F58 pause APIs. No execution can precede the broker result and pose audit.
  - Source commit 158b99df17a5a28b8da0d2780fdc71e06ff0c2ae; p84 symlink build passed in 1.50 seconds. p85 passed 2788 tests with zero errors, failures, or skips in about 84 seconds.
  - Installed/source module tree hash is d5040c0402485e96e1fd0a23683c1e0818ba6d82e206ac1505ad9c2e45864751; complete source hash is d91ad106d81e5b49a64109771318f0a94a0a26812896954e886973a06911c0aa; compileall and frozen input hashes passed.
  - F59 image sha256:000d73c29fc7b77e56e852b755db01a60f74b5a2e85b2150915af8512d5584f2 binds the exact source hash. Corrected build r2 exited 0 in 1.34 seconds. Corrected smoke r3 returned QUALIFIED CUDA for YOLO in 34.62 ms and Grounded-SAM in 193.78 ms and left no container or GPU process. The initial build exit-capture error and smoke path-preparation failures are retained as harness evidence and did not alter the qualifying artifacts.
  - Fresh EXP-058 preflight found 24 CPUs, 24.915 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged four-point execute gate with only consumer readiness moved before the immutable inference snapshot and no physics pause.
retained: EXP-057 evidence, F59 RED/GREEN/adjacent/build/package/provenance/image/smoke/preflight evidence, and all prior evidence
archived: none
deletion_candidates: F59 pytest, p84, and p85 scratch trees after readback; no deletion authorized
decision: RUN EXP-058
```

## EXP-058 — Task 14 prestarted-consumer pose freshness F59 two-Worker execute

```yaml
experiment_id: EXP-058
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T00:29:29+08:00
  - status: RUNNING
    at: 2026-09-13T00:29:29+08:00
  - status: INVALID
    at: 2026-09-13T00:31:07+08:00
prior_experiment: EXP-057
hypothesis: Starting and confirming each lease's exact dynamic consumer before its immutable inference snapshot gives both publisher and consumer adequate clock history while preserving the pose-freshness and action-authorization gates.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, every dynamic execution receipt is complete, and every recovery diagnostic is all true.
single_variable: The exact dynamic consumer is started and ready before the immutable inference snapshot and reused for execute_expert; F58 physics pause behavior is removed. Every source/config/model/point/timeout/freshness/physical criterion remains frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f59
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f59
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete recovery/dynamic receipts, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 158b99df17a5a28b8da0d2780fdc71e06ff0c2ae
  executable_source_tree: d91ad106d81e5b49a64109771318f0a94a0a26812896954e886973a06911c0aa
  installed_module_tree: d5040c0402485e96e1fd0a23683c1e0818ba6d82e206ac1505ad9c2e45864751
  image_id: sha256:000d73c29fc7b77e56e852b755db01a60f74b5a2e85b2150915af8512d5584f2
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp058.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f59 and root live-small-f59.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: INVALID — the command failed closed with PROVENANCE_MIXED_OVERLAY in 0.22 seconds before creating the batch root or starting ROS, Docker, GPU inference, simulation, or any physical action. The run wrapper incorrectly added the two pytest-only dependency environments to PYTHONPATH after sourcing the full worktree overlay. This is a command-environment transcription failure and does not test F59 behavior.
cleanup_readback: The intended batch root was absent; no related process, container, GPU compute application, or ROS domain 181-183 claim remained.
retained: command-058 log/time/exit, preflight, this diagnosis, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-051
last_valid_experiment: EXP-022
current_hypothesis: The F59 prestarted-consumer hypothesis remains untested because EXP-058 exited at provenance validation.
working_tree_status: clean executable source at 158b99df17a5a28b8da0d2780fdc71e06ff0c2ae; ledger-only EXP-059 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-058 created no batch root and started no ROS, Docker, GPU inference, simulation, or physical action.
  - A clean-shell readback after sourcing only /opt/ros/jazzy/setup.zsh and the complete worktree install/setup.zsh resolves so101_demo exclusively from the worktree build and contains no pytest-only dependency paths.
  - Fresh EXP-059 preflight found 24 CPUs, 24.983 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged F59 four-point gate under only the verified Jazzy underlay and complete worktree overlay. No implementation, config, model, point, timeout, or acceptance criterion changes.
retained: EXP-058 command evidence, clean-shell overlay readback, EXP-059 preflight, and all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: RUN EXP-059
```

## EXP-059 — Task 14 prestarted-consumer pose freshness F59 corrected overlay

```yaml
experiment_id: EXP-059
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T00:31:52+08:00
  - status: RUNNING
    at: 2026-09-13T00:31:52+08:00
  - status: INVALID
    at: 2026-09-13T00:32:48+08:00
prior_experiment: EXP-058
hypothesis: Starting and confirming each lease's exact dynamic consumer before its immutable inference snapshot gives both publisher and consumer adequate clock history while preserving the pose-freshness and action-authorization gates.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, every dynamic execution receipt is complete, and every recovery diagnostic is all true.
single_variable: No product or experimental variable differs from EXP-058; only the shell environment is corrected by removing the mistakenly appended pytest-only PYTHONPATH entries.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f59-r2
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f59-r2
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete recovery/dynamic receipts, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 158b99df17a5a28b8da0d2780fdc71e06ff0c2ae
  executable_source_tree: d91ad106d81e5b49a64109771318f0a94a0a26812896954e886973a06911c0aa
  installed_module_tree: d5040c0402485e96e1fd0a23683c1e0818ba6d82e206ac1505ad9c2e45864751
  image_id: sha256:000d73c29fc7b77e56e852b755db01a60f74b5a2e85b2150915af8512d5584f2
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp059.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f59-r2 and root live-small-f59-r2.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: INVALID — the clean-overlay command still failed closed with PROVENANCE_MIXED_OVERLAY in 0.20 seconds before creating the batch root or starting ROS, Docker, GPU inference, simulation, or any physical action. Source inspection identified the exact remaining transcription error: --points used the external handoff copy, while the product deliberately requires config and catalog paths beneath src/so101_demo_py. The package-local moveit_expert_validation_points_v1.yaml has the exact frozen c7491547 catalog hash.
cleanup_readback: The intended batch root was absent; no related process, container, GPU compute application, or ROS domain 181-183 claim remained.
retained: command-059 log/time/exit, source diagnosis, preflight, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-052
last_valid_experiment: EXP-022
current_hypothesis: The F59 prestarted-consumer hypothesis remains untested because EXP-059 exited at path provenance validation.
working_tree_status: clean executable source at 158b99df17a5a28b8da0d2780fdc71e06ff0c2ae; ledger-only EXP-060 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-059 created no batch root and started no ROS, Docker, GPU inference, simulation, or physical action.
  - Source readback proves _validate_provenance_overlay requires both config and points beneath src/so101_demo_py. The package-local moveit_expert_validation_points_v1.yaml is byte-for-byte hash-identical to the frozen handoff catalog at c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5.
  - Fresh EXP-060 preflight found 24 CPUs, 24.994 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged F59 four-point gate under the clean overlay with the exact-hash package-local catalog path required by the product provenance contract.
retained: EXP-059 command evidence, catalog path/hash diagnosis, EXP-060 preflight, and all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: RUN EXP-060
```

## EXP-060 — Task 14 prestarted-consumer pose freshness F59 corrected catalog path

```yaml
experiment_id: EXP-060
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T00:33:26+08:00
  - status: RUNNING
    at: 2026-09-13T00:33:26+08:00
  - status: INVALID
    at: 2026-09-13T00:50:50+08:00
prior_experiment: EXP-059
hypothesis: Starting and confirming each lease's exact dynamic consumer before its immutable inference snapshot gives both publisher and consumer adequate clock history while preserving the pose-freshness and action-authorization gates.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, every dynamic execution receipt is complete, and every recovery diagnostic is all true.
single_variable: No product or experimental variable differs from EXP-059; only --points is corrected to the package-local catalog copy carrying the exact frozen catalog hash.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f59-r3
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f59-r3
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete recovery/dynamic receipts, complete evidence, and clean shutdown.
provenance:
  executable_source_commit: 158b99df17a5a28b8da0d2780fdc71e06ff0c2ae
  executable_source_tree: d91ad106d81e5b49a64109771318f0a94a0a26812896954e886973a06911c0aa
  installed_module_tree: d5040c0402485e96e1fd0a23683c1e0818ba6d82e206ac1505ad9c2e45864751
  image_id: sha256:000d73c29fc7b77e56e852b755db01a60f74b5a2e85b2150915af8512d5584f2
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_path: src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp060.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f59-r3, root live-small-f59-r3, and package-local exact-hash catalog.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic or physical failure remains INVALID.
result: INVALID — exit 1 after 218.59 seconds. All four points physically PASSED with 19-state dynamic execution, exact YOLO-first accepted poses, upright stable table support, empty fingertip contacts, empty attachment state, centered target placement, and retreat. Each Worker completed exactly two leases and all four recovery receipts succeeded. Nevertheless qualification_passed=false because batch_cleanup_complete=false. Docker created the cidfile as mode 0664 while exact retirement requires 0600, so the Broker remained; after both Worker groups were proven reaped, shutdown also treated their already-closed control sockets as failures. The exact Broker was inspected, stopped by full container ID, and auto-removed.
broker_readback: Container d35ec49412a510ffda7d72462a8fc6c37f8fbe1c7d33b27ff9d65c73c9a27b56 matched exact F59 image/source/batch/generation labels, isolated network/IPC, read-only root, no-new-privileges, GPU request, UID:GID 1000:1000, and exact model/runtime/input mounts.
cleanup_readback: After exact manual Broker cleanup there was no related process, container, GPU compute application, or ROS domain 181-183 claim.
visual_readback: All eight authorized 640x480 RGB images were inspected at original resolution. Initial cups were upright outside target with reset arms; terminal cups were upright inside target with detached grippers and retreated arms. Visual outcome PASS.
retained: complete live-small-f59-r3 tree, command-060 log/time/exit, broker inspect/full summary, visual report, root-cause report, MuJoCo log, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-053
last_valid_experiment: EXP-022
current_hypothesis: Hardening Docker's exact cidfile before broker-ready acceptance and accepting already-proven reaped Worker groups as completed control cleanup will allow the same 4/4 physical outcome to seal batch_cleanup_complete=true.
working_tree_status: clean executable source at e371651a2da02edeb9480cb10f092861577f6b2a; ledger-only EXP-061 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-060 proves the F59 consumer-before-inference correction physically passed all four frozen points; only cleanup accounting prevented qualification.
  - Formal RED pytest-OhmycwHY failed both missing cleanup behaviors. Focused GREEN pytest-oW2KRie3 and pytest-APF01X14 passed, the complete CLI gate pytest-BSzdhv1o passed 65 tests, and the adjacent parallel suite passed 992 tests.
  - F60 validates the cidfile as same inode, regular, same UID, and exact 64-hex content before fchmod/fsync to 0600 in the broker-ready gate. It bypasses dead control RPC only after wait_for_children has positively reaped every Worker group; live Worker cleanup behavior is unchanged.
  - Source commit e371651a2da02edeb9480cb10f092861577f6b2a; p86 symlink build passed in 1.51 seconds. p87 is retained as an invalid test harness because its long randomized TMPDIR exceeded AF_UNIX limits and unscoped test-result read stale packages. Corrected short-path p88 passed 2790 tests with zero errors, failures, or skips in 83.48 seconds.
  - Installed/source module tree hash is f2f46a426e15110271aeb1e1d9915dfdbfac3473a9642620d540ebe588d513bb; complete source hash is cc24ca107638bbe9039f840a4b1af7c6ce1b9f311cbc3936c9cf1fcf6c681773; compileall and frozen input hashes passed.
  - F60 image sha256:24a0043a7c60968617d735bf3708890a814bb7b1b78ce4627d5c14f442c1c795 binds the exact source hash. Build exited 0 in 12.08 seconds; smoke returned QUALIFIED CUDA for YOLO in 38.41 ms and Grounded-SAM in 197.47 ms, with no residual container or GPU process.
  - Fresh EXP-061 preflight found 24 CPUs, 24.831 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged four-point execute gate with only exact Broker/Worker cleanup completion behavior changed.
retained: EXP-060 evidence, F60 RED/GREEN/adjacent/build/package/provenance/image/smoke/preflight evidence, and all prior evidence
archived: none
deletion_candidates: pytest-OhmycwHY, pytest-oW2KRie3, pytest-APF01X14, pytest-BSzdhv1o, the 992-test scratch, p86, p87, and p88 scratch trees after readback; no deletion authorized
decision: RUN EXP-061
```

## EXP-061 — Task 14 complete-cleanup F60 two-Worker execute

```yaml
experiment_id: EXP-061
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T00:51:10+08:00
  - status: RUNNING
    at: 2026-09-13T00:51:10+08:00
  - status: INVALID
    at: 2026-09-13T01:06:58+08:00
prior_experiment: EXP-060
hypothesis: The exact cidfile and reaped-Worker cleanup fixes preserve the 4/4 physical outcome while allowing automatic Broker retirement and batch cleanup completion.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, every recovery receipt succeeds, exact Broker auto-removes, and no owned task remains.
single_variable: Broker cidfile is hardened before readiness and cleanup skips dead RPC only after positive Worker-group reap proof. Every execution, source/config/model/point/timeout/freshness/physical criterion remains frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f60
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f60
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, complete recovery/dynamic receipts, batch_cleanup_complete=true, complete evidence, and no residual task.
provenance:
  executable_source_commit: e371651a2da02edeb9480cb10f092861577f6b2a
  executable_source_tree: cc24ca107638bbe9039f840a4b1af7c6ce1b9f311cbc3936c9cf1fcf6c681773
  installed_module_tree: f2f46a426e15110271aeb1e1d9915dfdbfac3473a9642620d540ebe588d513bb
  image_id: sha256:24a0043a7c60968617d735bf3708890a814bb7b1b78ce4627d5c14f442c1c795
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp061.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f60 and root live-small-f60.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, or cleanup failure remains INVALID.
result: INVALID — exit 1 after 284.28 seconds. All four point statuses are PASSED and all eight immutable 640x480 RGB images pass original-resolution inspection: every cup starts upright outside the target and ends upright inside it with the gripper detached and arm retreated. Three recovery receipts succeeded. The final worker-02 recovery after sample_14_far_right failed because ros2_control_node aborted with exit -6 while sending a controller-manager service response; gripper_controller consequently did not become active and the recovery receipt is false. Broker retirement separately hit an idempotency race: exact ownership inspection succeeded, Docker auto-removed the container before docker stop completed, and F60 treated the nonzero stop result as cleanup failure despite verified absence. Therefore batch_cleanup_complete=false and qualification_passed=false.
cleanup_readback: The cidfile is exact owner mode 0600. No related process, running container, GPU compute application, or ROS domain 181-183 claim remains. The Broker was already auto-removed; no manual destructive action was needed.
visual_readback: All eight authorized 640x480 RGB images were inspected at original resolution. Initial cups were upright outside target with reset arms; terminal cups were upright inside target with detached grippers and retreated arms. Visual outcome PASS.
retained: complete live-small-f60 tree, command-061 log/time/exit, visual report, root-cause report, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-054
last_valid_experiment: EXP-022
current_hypothesis: F61's idempotent exact Broker retirement will preserve verified ownership while accepting the already-absent post-inspect Docker state; the unrelated final Worker recovery abort in EXP-061 was transient and should not recur under the unchanged recovery implementation.
working_tree_status: clean executable source at bcf538fbb57a056f4edc01da5f09193afc9e3ebb; ledger-only EXP-062 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-061 again physically passed all four frozen points, including complete original-resolution visual evidence, but is INVALID because only three of four recovery receipts succeeded and batch cleanup remained false.
  - The failed final recovery is directly explained by a controller-manager rclcpp response-publication abort; it did not alter any already-sealed PASSED point and left no runtime residue.
  - F61 changes only exact Broker retirement: a nonzero docker stop is accepted only when the mandatory after-inspect proves the exact container absent; it remains a failure when the container is still present.
  - Formal RED pytest-UHF9IPBT reproduced the inspect/stop disappearance race. Focused GREEN passed four tests and the adjacent parallel suite passed 993 tests.
  - Source commit bcf538fbb57a056f4edc01da5f09193afc9e3ebb; p89 symlink build passed in 1.50 seconds. Corrected p90 passed 2791 ordinary package tests with zero errors, failures, or skips in 83.41 seconds using registered scratch.
  - Installed/source module tree hash is 61008539abdc8c5f870a7f31177dc1eead7f0f4c7831e85f567c5459ce2eee7d; complete source hash is 4f2195b04fcb749c0311c7af97a0d88e0a747af3ff540362b81c1354e90c4a7b.
  - F61 image sha256:755538c1270ebbe5d9ce8b561e2d536079cd49bc5eb6cbe2f67687d2fd5a5d7e binds the exact source hash. Build exited 0 in 13.00 seconds; smoke returned QUALIFIED CUDA for YOLO in 31.15 ms and Grounded-SAM in 172.89 ms, with no residual container or GPU process.
  - Fresh EXP-062 preflight found 24 CPUs, 24.827 GiB MemAvailable, 15269 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged four-point execute gate with only idempotent exact Broker retirement changed. Do not change the recovery implementation unless the same controller-manager fault reproduces.
retained: EXP-061 evidence, F61 RED/GREEN/adjacent/build/package/provenance/image/smoke/preflight evidence, and all prior evidence
archived: none
deletion_candidates: pytest-UHF9IPBT, focused/adjacent F61 test scratches, p89, and p90 scratch trees after readback; no deletion authorized
decision: RUN EXP-062
```

## EXP-062 — Task 14 idempotent Broker retirement F61 two-Worker execute

```yaml
experiment_id: EXP-062
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T01:06:58+08:00
  - status: RUNNING
    at: 2026-09-13T01:06:58+08:00
  - status: INVALID
    at: 2026-09-13T01:15:30+08:00
prior_experiment: EXP-061
hypothesis: Treating a verified already-absent Broker as successfully retired preserves exact ownership fencing while allowing the unchanged four-point physical and recovery path to qualify.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, all four recovery receipts succeed, exact Broker auto-removes, and no owned task remains.
single_variable: Exact Broker retirement accepts docker stop failure only when mandatory after-inspect proves the exact container absent. Every Worker recovery, execution, source/config/model/point/timeout/freshness/physical criterion remains frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f61
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f61
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recovery/dynamic receipts complete and successful, batch_cleanup_complete=true, complete evidence, and no residual task.
provenance:
  executable_source_commit: bcf538fbb57a056f4edc01da5f09193afc9e3ebb
  executable_source_tree: 4f2195b04fcb749c0311c7af97a0d88e0a747af3ff540362b81c1354e90c4a7b
  installed_module_tree: 61008539abdc8c5f870a7f31177dc1eead7f0f4c7831e85f567c5459ce2eee7d
  image_id: sha256:755538c1270ebbe5d9ce8b561e2d536079cd49bc5eb6cbe2f67687d2fd5a5d7e
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp062.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f61 and root live-small-f61.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, recovery, or cleanup failure remains INVALID.
result: INVALID — exit 1 after 194.46 seconds. task_start and sample_05_near_center PASSED with visually correct terminal placement. worker-02's cup_test_forward_5cm consumer emitted READY, but the late-created /cup_pose publisher did not deliver the single pose before being destroyed; the consumer timed out after 5.0 seconds and execute_expert raised POSE_ACCEPTED_PUBLICATION_FAILED. The conservative action-may-have-started boundary sealed this point INDETERMINATE; recovery fenced the generation but could not prove stopped or confirmed, so worker-02 was quarantined. worker-01 then reached K=2 and sample_14_far_right remained UNRUN. The batch is nonterminal, cleanup cannot qualify, and qualification_passed=false.
cleanup_readback: No related process, running container, GPU compute application, or ROS domain 181-183 claim remains. The exact F61 Broker auto-removed without manual action.
visual_readback: All five available immutable 640x480 RGB images were inspected at original resolution. The two PASSED points have correct initial and terminal frames. The INDETERMINATE point has only a correct initial frame; the UNRUN point has none. Visual outcome PARTIAL_PASS_INVALID_BATCH.
retained: complete live-small-f61 tree, command-062 log/time/exit, visual report, root-cause report, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment; no deletion authorized
```

```yaml
checkpoint_id: CP-055
last_valid_experiment: EXP-022
current_hypothesis: Priming one isolated /cup_pose publisher during exact consumer readiness and retaining it through publication will eliminate late DDS/clock discovery loss without changing pose, authorization, or motion policy.
working_tree_status: clean executable source at bcf538fbb57a056f4edc01da5f09193afc9e3ebb; bounded F62 TDD correction follows
owned_processes: NONE
confirmed_conclusions:
  - EXP-062 reproduced the previously latent consumer/publisher race: consumer readiness alone does not make a newly created publisher's one message durable across a 50 ms lifetime under parallel load.
  - The failed Worker emitted status=READY, then CUP_POSE_TIMEOUT, while execute_expert reported POSE_ACCEPTED_PUBLICATION_FAILED. It never produced a terminal RGB or dynamic execution manifest.
  - The unchanged conservative recovery behavior fenced and quarantined the uncertain Worker; the second Worker continued independently to K=2 and passed both points.
  - Five available RGB frames pass original-resolution inspection, and post-run readback proves no process, container, GPU task, or domain claim remains.
ruling: F62 may keep a Worker-local isolated ROS publisher alive from consumer readiness through recovery/close, pre-spinning its /clock and DDS graph before inference. It must preserve the exact /cup_pose payload, source timestamp, subscriber count requirement, run-mode authorization, recovery fencing, and all physical criteria. Direct tests must prove prewarm, retention, exact close/rebind cleanup, and fail-closed behavior.
retained: EXP-062 runtime, visual, root-cause, and cleanup evidence plus all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: IMPLEMENT F62 WITH TDD; do not start another live experiment until focused, adjacent, package, build, provenance, image, smoke, and fresh preflight gates pass.
```

```yaml
checkpoint_id: CP-056
last_valid_experiment: EXP-022
current_hypothesis: F62's primed retained pose publisher removes the reproduced late-publisher loss while preserving all safety, recovery, and physical contracts.
working_tree_status: clean executable source at 99a54199cbd2823254732f0da741f2153670dcc9; ledger-only EXP-063 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - Formal RED pytest-F5M6nnPb proved the old consumer-ready path did not create a publisher. Focused GREEN pytest-mHraPB5c passed four tests after the correction.
  - pytest-38KiYUMU is retained as an invalid test harness: the partial setup resolved mujoco_ros2_control_msgs from /opt/ros instead of the worktree. The corrected full-overlay pytest-VJJBiphQ passed all 23 ROS runtime tests.
  - The complete adjacent parallel suite pytest-Rdyomqc8 passed 1043 tests in 41.63 seconds.
  - F62 pre-creates a private-context /cup_pose publisher only after the exact consumer graph is present, requires exactly one matched subscriber and a nonzero simulation clock, retains the publisher through the publish, and closes it on recovery rebind or runtime close. The direct non-primed path remains unchanged.
  - Source commit 99a54199cbd2823254732f0da741f2153670dcc9; p91 symlink build passed in 1.51 seconds. p92 passed 2792 ordinary package tests with zero errors, failures, or skips in 83.49 seconds using registered scratch.
  - Installed/source module tree hash is 92d8ed122f8879190c3e4ea3221b9318be595255eb52fb2343eaa54e40159923; complete source hash is e81e3b738ed7826206c59d6c31ddb5a481ed3eef5e5572642c79d03c41b4ba59; compileall and frozen input hashes passed.
  - F62 image sha256:6c46f0a9d0d3d910ae74ff4491ef20e3996d9169ad49f418dc61bb2cb686c5ef binds the exact source hash. Build exited 0; smoke returned QUALIFIED CUDA for YOLO in 32.70 ms and Grounded-SAM in 191.80 ms, with no residual container or GPU process.
  - Fresh EXP-063 preflight found 24 CPUs, 24.695 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, and all domains unlocked.
ruling: Repeat the unchanged four-point execute gate with only the F62 publisher lifetime correction added to the already-tested F61 cleanup behavior.
retained: F62 RED/GREEN/invalid-harness/adjacent/build/package/provenance/image/smoke/preflight evidence, EXP-062 MuJoCo log, and all prior evidence
archived: none
deletion_candidates: pytest-F5M6nnPb, pytest-mHraPB5c, pytest-38KiYUMU, pytest-VJJBiphQ, pytest-Rdyomqc8, p91, and p92 scratch trees after readback; no deletion authorized
decision: RUN EXP-063
```

## EXP-063 — Task 14 retained pose publisher F62 two-Worker execute

```yaml
experiment_id: EXP-063
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T01:26:53+08:00
  - status: RUNNING
    at: 2026-09-13T01:26:53+08:00
  - status: INVALID
    at: 2026-09-13T01:36:58+08:00
prior_experiment: EXP-062
hypothesis: A publisher whose DDS match and simulation clock are established before inference and whose lifetime extends beyond the single publish will deliver every accepted pose without weakening any execution gate.
prediction: Four unique points finish PASSED with qualification_passed=true, each slot uses no more than two leases, all four recovery receipts succeed, exact Broker auto-removes, and no owned task remains.
single_variable: Worker-local /cup_pose publisher setup moves into consumer readiness and its isolated owner is retained until recovery/close. Every Broker, recovery, execution, source/config/model/point/timeout/freshness/physical criterion remains frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f62
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f62
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recovery/dynamic receipts complete and successful, batch_cleanup_complete=true, complete evidence, and no residual task.
provenance:
  executable_source_commit: 99a54199cbd2823254732f0da741f2153670dcc9
  executable_source_tree: e81e3b738ed7826206c59d6c31ddb5a481ed3eef5e5572642c79d03c41b4ba59
  installed_module_tree: 92d8ed122f8879190c3e4ea3221b9318be595255eb52fb2343eaa54e40159923
  image_id: sha256:6c46f0a9d0d3d910ae74ff4491ef20e3996d9169ad49f418dc61bb2cb686c5ef
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp063.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: >-
  The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f62 and root live-small-f62.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, recovery, or cleanup failure remains INVALID.
result: INVALID — exit 1 after 242.73 seconds. All four unique points passed, all four recovery receipts succeeded, both Workers remained within K=2, and all eight original-resolution RGB frames passed visual inspection. The coordinator reached POINTS_COMPLETE, but batch_cleanup_complete remained false. Post-run readback found an empty owned-process manifest and no related process, container, GPU task, or domain claim. Because the current composition collapses supervisor and container cleanup into one boolean while swallowing component exceptions, the retained run cannot identify which exact cleanup sub-gate failed.
retained: complete live-small-f62 tree, command-063 log/time/exit, visual report, root-cause report, cleanup audit, MuJoCo log, and all prior evidence
archived: none
deletion_candidates: none from this experiment yet
```

```yaml
checkpoint_id: CP-057
last_valid_experiment: EXP-022
current_hypothesis: A private immutable per-component cleanup receipt will expose the exact strict cleanup sub-gate responsible for EXP-063 without changing scheduling, motion, perception, recovery, or qualification semantics.
working_tree_status: executable source remains clean at 99a54199cbd2823254732f0da741f2153670dcc9; ledger and EXP-063 reports are the only pending records before bounded F63 TDD instrumentation
owned_processes: NONE
confirmed_conclusions:
  - EXP-063 physically passed all four points and all eight original-resolution visual checks; every recovery receipt succeeded.
  - POINTS_COMPLETE was durable, but no BATCH_CLEANUP_COMPLETE event was emitted and qualification_passed remained false.
  - Post-run readback proves the owned manifest is empty and no related process, exact Broker container, GPU task, or domain claim remains.
  - Existing retained evidence does not distinguish process_cleanup=false from container_cleanup=false because the composition swallows component exceptions and emits only the aggregate qualification document.
ruling: Add fail-closed, mode-0600 cleanup-gates.json diagnostics under the already-private batch evidence root. Record named shutdown-action results, process_cleanup, container_cleanup, and exception class/message; never turn a false or exceptional gate into success. Prove the receipt with RED/GREEN tests, then repeat the unchanged four-point execute gate under fresh provenance.
retained: EXP-063 runtime, visual, root-cause, cleanup, MuJoCo, and command evidence plus all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: IMPLEMENT F63 DIAGNOSTIC WITH TDD; do not run fault injection or full validation until a fresh small gate qualifies.
```

```yaml
checkpoint_id: CP-058
last_valid_experiment: EXP-022
current_hypothesis: F63 will preserve the four-point physical success while emitting the exact cleanup component responsible for a failure, or will qualify if every strict component succeeds.
working_tree_status: clean executable source at 09d334fa97d5220c6061779f251d368ec875afaf; ledger-only EXP-064 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - Formal RED pytest-SN6MM2Hr failed because cleanup-gates.json did not exist. Focused GREEN pytest-GTGLf7nA passed 14 tests; the combined CLI/process suite pytest-n1q9mBJ5 passed 78 tests.
  - pytest-sEKIJgej is retained as an invalid partial-overlay harness (1042 pass, one /opt/ros FreeJointState import failure). Corrected full-overlay pytest-4xgrQIXH passed all 1043 adjacent parallel tests in 41.54 seconds.
  - F63 records named action results, supervisor process cleanup, exact Broker container cleanup, coordinator completion, exception types/messages, and the final cleanup bit in private cleanup-gates.json. Every false or exception remains fail-closed.
  - Commit 09d334fa97d5220c6061779f251d368ec875afaf; p93 build passed in 1.49 seconds. p94 is an invalid bare dependency harness; corrected p95 passed 2792 ordinary package tests with zero errors, failures, or skips in 82.08 seconds.
  - Source/install module hashes both equal 7bae5d97bdc0357849db4d107549ac3cc390cc62f0e5a41a744dd5b2aa8ad422; complete source hash is a4910c8116c003f5da5c8221432f29d41c1ca215086682a0c9fa4bde9623aca9.
  - F63 image sha256:c9ad87b0d8094c771c578b95e4d6e5aaf875844368affb6a0e3750542ec5f544 binds the exact source. The first smoke is invalid only because wrapper umask left cidfile 0664; fresh smoke-r2 has private evidence and QUALIFIED CUDA results for YOLO (32.66 ms inference) and Grounded-SAM (150.20 ms inference), with no residual container or GPU process.
  - Fresh EXP-064 preflight found 24 CPUs, 24.664 GiB MemAvailable, 15272 MiB free GPU, no related process/container/GPU task, and no extant domain claim.
ruling: Repeat the unchanged four-point execute gate with F63 diagnostics. Do not proceed to controlled faults or the 20-point batch unless physical, recovery, visual, cleanup, and residual gates all pass.
retained: F63 RED/GREEN/invalid-harness/adjacent/build/package/provenance/image/smoke/preflight evidence, EXP-063 complete evidence, and all prior evidence
archived: none
deletion_candidates: pytest-SN6MM2Hr, pytest-yDSZPEOy, pytest-GTGLf7nA, pytest-n1q9mBJ5, pytest-sEKIJgej, pytest-4xgrQIXH, p93, p94, and p95 scratch trees after readback; no deletion authorized
decision: RUN EXP-064
```

## EXP-064 — Task 14 cleanup-component receipt F63 two-Worker execute

```yaml
experiment_id: EXP-064
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T01:48:43+08:00
  - status: RUNNING
    at: 2026-09-13T01:48:43+08:00
  - status: INVALID
    at: 2026-09-13T01:58:41+08:00
prior_experiment: EXP-063
hypothesis: Private per-component cleanup evidence will either prove every strict cleanup sub-gate and permit qualification or identify the exact remaining failure without ambiguity.
prediction: Four unique points finish PASSED with qualification_passed=true, every recovery receipt succeeds, cleanup-gates.json reports every component true, and no owned task remains.
single_variable: Addition of fail-closed cleanup diagnostics; all scheduling, perception, pose, motion, recovery, timeout, source/config/model/catalog, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f63
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f63
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recoveries and visuals pass, cleanup receipt entirely true, and no residual task.
provenance:
  executable_source_commit: 09d334fa97d5220c6061779f251d368ec875afaf
  executable_source_tree: a4910c8116c003f5da5c8221432f29d41c1ca215086682a0c9fa4bde9623aca9
  installed_module_tree: 7bae5d97bdc0357849db4d107549ac3cc390cc62f0e5a41a744dd5b2aa8ad422
  image_id: sha256:c9ad87b0d8094c771c578b95e4d6e5aaf875844368affb6a0e3750542ec5f544
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp064.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f63 and root live-small-f63.
acceptance: The complete frozen Task 14 live-small gate plus the F63 cleanup receipt; any diagnostic, physical, recovery, visual, or residual failure remains INVALID.
result: >-
  INVALID — exit 1 after 256.16 seconds. task_start passed on worker-01. The first
  cup_test_forward_5cm attempt failed closed before physical action because the dynamic consumer
  printed READY for /cup_pose but the shell-based ROS graph probe did not observe its subscription;
  worker-02 recovery then succeeded and the point passed on worker-01 lease 2. That final point's
  recovery failed when the replacement ros2_control_node exited -6 and joint_state_broadcaster was
  not active, leaving sample_05_near_center and sample_14_far_right UNRUN. All five available
  original-resolution RGB frames passed visual inspection. F63 conclusively separated cleanup:
  all four actions, process cleanup, and exact Broker-container cleanup succeeded; coordinator
  completion was correctly not attempted because the batch was nonterminal. Post-run readback found
  no related process, container, GPU task, or domain claim.
retained: complete live-small-f63 tree, command-064 log/time/exit, visual report, root-cause report, cleanup audit, MuJoCo log, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-059
last_valid_experiment: EXP-022
current_hypothesis: Worker-local rclpy graph identity plus exact retained-publisher DDS matching and a nonzero simulation clock will eliminate the external ros2 node info false negative without weakening consumer readiness.
working_tree_status: clean executable source at 09d334fa97d5220c6061779f251d368ec875afaf; ledger-only EXP-064 closure is pending before bounded F64 TDD
owned_processes: NONE
confirmed_conclusions:
  - EXP-064 produced two PASSED physical points, one fail-closed pre-action INVALID attempt, and two UNRUN points; all five available original-resolution RGB frames passed.
  - The failed dynamic consumer itself printed READY for /cup_pose, but consumer_ready did not see the subscription through repeated shell ros2 node info probes and the child later timed out without a pose.
  - F63 cleanup diagnostics are conclusive: every named action, process cleanup, and exact container cleanup succeeded. batch_cleanup_complete is false only because coordinator completion was inapplicable to a nonterminal batch.
  - The final worker-01 recovery independently failed after ros2_control_node exited -6 and joint_state_broadcaster remained inactive. Preserve this as a separate diagnosis; do not mix a recovery retry change into F64.
  - Post-run evidence proves an empty owned-process manifest, absent exact Broker container, no related process or GPU application, and absent domain claims 181/182/183.
  - F64 formal RED pytest-nDnveglx failed because the old implementation instantiated the forbidden shell graph probe. Focused GREEN pytest-wI6E4zJg passed; the first full-file run pytest-a7ya6NDw is retained as an invalid partial-overlay harness, while corrected full-overlay pytest-tyjwt3cX passed all 23 tests and adjacent parallel suite pytest-uteanrIG passed all 1043 tests in 41.99 seconds.
ruling: TDD one bounded F64 change to consumer readiness only. Prime and retain the isolated publisher, use its worker-local rclpy graph to require the exact dynamic consumer identity, require exactly one DDS subscription match and nonzero simulation clock, and remove the shell graph probe from this gate. Repeat the unchanged four-point gate before addressing any recurring recovery-start defect.
retained: EXP-064 complete runtime, visual, root-cause, cleanup, MuJoCo, and command evidence plus all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: IMPLEMENT F64 CONSUMER READINESS WITH TDD
```

```yaml
checkpoint_id: CP-060
last_valid_experiment: EXP-022
current_hypothesis: F64's worker-local graph observation will deliver the pose to every already-ready dynamic consumer while preserving exact identity, DDS matching, simulation-clock, recovery, and cleanup gates.
working_tree_status: clean at 3a5669fd66009521ba1d99bef586b7df9dc2d0a7; ledger-only EXP-065 preregistration follows
owned_processes: NONE
confirmed_conclusions:
  - F64 commit 3a5669fd66009521ba1d99bef586b7df9dc2d0a7 primes the isolated publisher before readiness polling, requires exactly one /so101_dynamic_cup_pick_place identity in its local rclpy graph, exactly one DDS subscription match, and a nonzero simulation clock; failure and timeout still close the publisher and fail closed.
  - Formal RED pytest-nDnveglx failed on the old shell probe. Focused GREEN pytest-wI6E4zJg passed; corrected full-overlay file gate pytest-tyjwt3cX passed 23 tests, adjacent gate pytest-uteanrIG passed 1043 tests, and ordinary package gate pytest-UNRf28de passed 2792 tests with zero errors, failures, or skips. pytest-a7ya6NDw is retained as an invalid partial-overlay harness.
  - p96 built so101_demo_py in 1.51 seconds using scratch/p96-nYIUzWEx/tmp. Source/install module hashes both equal 02c4eed8ea007e60d69eca62518c81d6f82ab11bd7470cbce78df80a20f4c79c; complete package source hash is fbe58f395a974775fba5faba44e1de16f0d9d87a883219640172580b8b5265a5.
  - The immutable F64 Broker image is sha256:941c3cff66abce090120a45d2f95c4a3a99c9095f114963b2adab59e2cb30f3f with matching internal source hash. Offline smoke returned QUALIFIED CUDA outcomes for YOLO at 34.0182 ms and Grounded-SAM at 191.692336 ms inference latency; evidence modes were private and no container or GPU task remained.
  - Fresh preflight capacity is 24 CPUs, 24.597 GiB MemAvailable, and 15269 MiB free GPU, with no related process/container/GPU application and no extant domain claim.
ruling: Repeat the unchanged four-point two-Worker execute gate with only the F64 readiness observation changed. Treat any dynamic, recovery, physical, visual, cleanup, or residual failure as INVALID; do not mask the separately retained recovery-start issue.
retained: F64 RED/GREEN/invalid-harness/full-overlay/adjacent/build/package/provenance/image/smoke/preflight evidence, EXP-064 complete evidence, and all prior evidence
archived: none
deletion_candidates: pytest-nDnveglx, pytest-wI6E4zJg, pytest-a7ya6NDw, pytest-tyjwt3cX, pytest-uteanrIG, pytest-UNRf28de, and p96 scratch trees after readback; no deletion authorized
decision: RUN EXP-065
```

## EXP-065 — Task 14 worker-local consumer readiness F64 two-Worker execute

```yaml
experiment_id: EXP-065
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T02:07:47+08:00
  - status: RUNNING
    at: 2026-09-13T02:07:47+08:00
  - status: INVALID
    at: 2026-09-13T02:14:53+08:00
prior_experiment: EXP-064
hypothesis: Worker-local rclpy graph identity plus exact retained-publisher DDS matching and a nonzero simulation clock will eliminate the external graph-probe false negative without weakening consumer readiness.
prediction: Four unique points finish PASSED with qualification_passed=true, every recovery receipt succeeds, cleanup-gates.json reports every component true, and no owned task remains.
single_variable: consumer_ready no longer shells out to ros2 node info; the retained publisher's isolated rclpy node observes exact consumer identity, exact DDS matching, and simulation clock. All scheduling, perception, pose, motion, recovery, timeout, source/config/model/catalog, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f64
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f64
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recoveries and visuals pass, cleanup receipt entirely true, and no residual task.
provenance:
  executable_source_commit: 3a5669fd66009521ba1d99bef586b7df9dc2d0a7
  executable_source_tree: fbe58f395a974775fba5faba44e1de16f0d9d87a883219640172580b8b5265a5
  installed_module_tree: 02c4eed8ea007e60d69eca62518c81d6f82ab11bd7470cbce78df80a20f4c79c
  image_id: sha256:941c3cff66abce090120a45d2f95c4a3a99c9095f114963b2adab59e2cb30f3f
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp065.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f64 and root live-small-f64.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, recovery, visual, cleanup, or residual failure remains INVALID.
result: >-
  INVALID — exit 1 after 213.42 seconds. F64 removed the consumer-readiness failure: both
  consumers printed READY, task_start and cup_test_forward_5cm passed, both recovery receipts
  succeeded, and all four available original-resolution RGB frames passed. worker-02 registered
  with the coordinator but returned WORKER_NOT_READY before a lease, with no owned task-station
  identity and no ROS log tree; worker-01 then reached its frozen K=2 limit, leaving two points
  UNRUN. The first bad boundary is task-station process start/identity registration, before
  motion-stack readiness. Cleanup diagnostics additionally recorded exact Broker-container cleanup
  false with BROKER_CONTAINER_SURVIVED, although later exact-ID readback proved it auto-removed.
  No related process, container, GPU task, or domain claim remained.
retained: complete live-small-f64 tree, command-065 log/time/exit, visual report, root-cause report, cleanup audit, MuJoCo log, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-061
last_valid_experiment: EXP-022
current_hypothesis: A short retry limited to transient incomplete /proc identity reads while the exact Popen child remains alive will prevent one Worker from being discarded during concurrent fork/exec without weakening PGID or PID-reuse safety.
working_tree_status: clean executable source at 3a5669fd66009521ba1d99bef586b7df9dc2d0a7; ledger-only EXP-065 closure is pending before bounded F65 TDD
owned_processes: NONE
confirmed_conclusions:
  - F64 is validated at its intended boundary: both dynamic consumers printed READY, both attempted points passed, and neither CUP_POSE_TIMEOUT nor consumer readiness failure recurred.
  - worker-02 registered first but returned WORKER_NOT_READY before a lease. Its owned runtime manifest is empty and no ROS log directory exists, localizing failure before first task-station identity publication rather than at motion_stack_ready.
  - WorkerOwnedProcessTree currently performs exactly one immediate /proc identity read after Popen. A transient empty cmdline during fork/exec is therefore fatal and is the narrowest code path consistent with the evidence, although the swallowed registration exception means EXP-065 cannot distinguish it from immediate Popen failure.
  - worker-01 passed two points and both recoveries. Its K=2 cap then correctly yielded NO_POINT because worker-02 had exited, leaving the remaining two points UNRUN.
  - Cleanup actions and process cleanup passed. Exact container cleanup timed out with BROKER_CONTAINER_SURVIVED, but the exact container was absent at post-run audit; no process, GPU task, or domain claim remained.
  - F65 formal RED pytest-sFz6pw5J failed on the first transient incomplete identity exception. Focused GREEN pytest-FQdXkTXl passed both the retry and immediate wrong-PGID rejection tests; full worker-runtime file pytest-TAQlLWZF passed 51 tests and adjacent parallel suite pytest-Vu2t237L passed 1044 tests in 41.76 seconds.
ruling: TDD only transient identity acquisition stabilization in WorkerOwnedProcessTree. Retry probe exceptions briefly while the exact child remains alive; immediately reject any successfully observed wrong PGID or incomplete successful identity; preserve exact process ownership, reaping, and cleanup semantics. Repeat the unchanged four-point gate before considering the independently retained container-retirement timing issue.
retained: EXP-065 complete runtime, visual, root-cause, cleanup, MuJoCo, and command evidence plus all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: IMPLEMENT F65 PROCESS IDENTITY STABILIZATION WITH TDD
```

```yaml
checkpoint_id: CP-062
last_valid_experiment: EXP-022
current_hypothesis: The bounded retry for transient incomplete /proc identity reads while the exact Popen child remains alive will allow both Workers to retain their task-station process identities under concurrent fork/exec without weakening wrong-PGID or PID-reuse rejection.
working_tree_status: clean executable source at a0524c3d4f80d7b3589990b397770a32df669f90; F65 build, package, immutable-image, and dual-model CUDA smoke gates all pass
owned_processes: NONE
confirmed_conclusions:
  - F65 formal RED pytest-sFz6pw5J failed at the intended transient incomplete-identity boundary; focused GREEN pytest-FQdXkTXl passed the retry and immediate wrong-PGID rejection cases.
  - The full worker-runtime file passed 51 tests, the adjacent parallel suite passed 1044 tests, and the ordinary package gate passed 2793 tests with zero failures or errors.
  - The fresh worktree overlay source/install hashes are c93d932332a87dda1e373468c13d5101848de4d2e4122228be3d8a17791eb37f and 01d0ac21c23dd640965b4fd8f2712682ca558b39f23cb07eb50e8c36394a5401.
  - Immutable image sha256:dee3dd0147cc8c62a2e145491c2512788905d4d61fe8b6903e92c028a8bcd3d2 independently reports the exact F65 source hash.
  - The isolated F65 smoke executed both models on CUDA: YOLO and Grounded-SAM returned QUALIFIED, and no container, related process, GPU compute application, or domain claim remained.
ruling: Repeat the unchanged frozen four-point two-Worker gate with F65 as the sole executable variable. Preserve all point selection, K=2, perception, pose, motion, recovery, cleanup, visual, model, image, config, catalog, and physical acceptance criteria.
retained: all F65 source, build, test, image, smoke, provenance, and prior experiment evidence
archived: none
deletion_candidates: all registered pytest/build scratch trees remain deletion candidates; no deletion authorized
decision: RUN EXP-066 UNCHANGED FOUR-POINT GATE
```

## EXP-066 — F65 stable Worker process-identity four-point gate

```yaml
experiment_id: EXP-066
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T02:24:33+08:00
  - status: RUNNING
    at: 2026-09-13T02:24:33+08:00
  - status: INVALID
    at: 2026-09-13T02:33:54+08:00
prior_experiment: EXP-065
hypothesis: A short retry limited to transient incomplete /proc identity reads while the exact Popen child remains alive will prevent either Worker from being discarded during concurrent task-station fork/exec.
prediction: Four unique points finish PASSED with qualification_passed=true, every recovery receipt succeeds, cleanup-gates.json reports every component true, and no owned task remains.
single_variable: WorkerOwnedProcessTree start identity acquisition retries only transient incomplete identity exceptions while the exact child remains alive. All scheduling, consumer readiness, perception, pose, motion, recovery, timeout, source/config/model/catalog, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f65
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f65
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recoveries and visuals pass, cleanup receipt entirely true, and no residual task.
provenance:
  executable_source_commit: a0524c3d4f80d7b3589990b397770a32df669f90
  executable_source_tree: c93d932332a87dda1e373468c13d5101848de4d2e4122228be3d8a17791eb37f
  installed_module_tree: 01d0ac21c23dd640965b4fd8f2712682ca558b39f23cb07eb50e8c36394a5401
  image_id: sha256:dee3dd0147cc8c62a2e145491c2512788905d4d61fe8b6903e92c028a8bcd3d2
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp066.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f65 and root live-small-f65.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, recovery, visual, cleanup, or residual failure remains INVALID.
result: >-
  INVALID — exit 1 after 194.77 seconds. F65 passed its intended boundary: both Workers
  registered task-station process identities and created ROS log trees. worker-01 then failed
  before its first lease when ros2_control_node threw an unhandled rclcpp::exceptions::RCLError
  while sending a controller-manager service response (`cannot publish data`) and aborted with
  exit -6. worker-02 passed task_start and cup_test_forward_5cm with both recoveries true, then
  reached K=2, leaving sample_05_near_center and sample_14_far_right UNRUN. All four available
  original-resolution 640x480 RGB frames passed visual inspection. Cleanup actions and process
  cleanup passed; exact container cleanup reported BROKER_CONTAINER_SURVIVED, but the exact-ID
  post-run audit proved that it auto-removed. No related process, container, GPU task, or domain
  claim remained.
retained: complete live-small-f65 tree, command-066 log/time/exit, visual report, root-cause report, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-063
last_valid_experiment: EXP-022
current_hypothesis: Repeated ListControllers readiness requests overlap controller-spawner startup and expose the documented Fast DDS basic-service discovery/response race; waiting for all required service/action graph endpoints before issuing the controller-state request will remove that overlap without weakening readiness.
working_tree_status: clean executable source at a0524c3d4f80d7b3589990b397770a32df669f90; ledger-only EXP-066 closure pending bounded F66 TDD
owned_processes: NONE
confirmed_conclusions:
  - F65 process-identity stabilization is validated at its exact boundary because both Workers registered task-station identities and produced ROS log trees.
  - worker-01 ros2_control_node completed MuJoCo/EGL initialization and scene readback, then aborted in the controller-manager service execution stack with `failed to send response: cannot publish data` before any lease.
  - At failure, joint_state_broadcaster had activated and exited while arm_controller and gripper_controller spawners were still waiting; the concurrently started motion_stack_ready client polls ListControllers once per loop before required action endpoints exist.
  - ROS 2 upstream reports the same Jazzy `/controller_manager/list_controllers` response failure and documents a Fast DDS basic-service discovery race that is exacerbated when many nodes launch together.
  - worker-02 passed two physical points and both recoveries; all four available images passed. Exact post-run audit found no residual owned task.
  - The independent Broker retirement observation race recurred and remains separate from the first bad boundary.
ruling: TDD one bounded F66 readiness-ordering change. motion_stack_ready must establish all required MoveIt service and action graph endpoints before it sends a ListControllers request, retain the exact controller-active checks and bounded deadline, and avoid overlapping controller-state requests. Repeat the unchanged four-point gate after full static/image/smoke qualification.
retained: EXP-066 runtime, visual, root-cause, cleanup, command, and upstream diagnostic evidence plus all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: IMPLEMENT F66 READINESS REQUEST ORDERING WITH TDD
```

```yaml
checkpoint_id: CP-064
last_valid_experiment: EXP-022
current_hypothesis: Gating ListControllers on the complete required service/action graph and retaining at most one pending controller query will avoid overlapping controller-manager startup traffic and eliminate the observed service-response abort.
working_tree_status: clean executable source at 51baa98b6256c05c69c82208d926dfcce115f6b3; F66 build, complete package, immutable-image, and dual-model CUDA smoke gates pass
owned_processes: NONE
confirmed_conclusions:
  - F66 RED pytest-IvhtUDE5 failed at both intended interfaces; focused GREEN pytest-bdw9muzs passed all six readiness tests.
  - The readiness/Worker adjacent gate passed 80 tests, the parallel suite passed 1044 tests, and the complete ordinary package gate passed 2795 tests with no errors, failures, or skips.
  - The complete source hash is e202be7120f08db46f1421ff5db1716d8a853dc3b9fdffa9017a0d1a9ab9f0ad and source/install module hashes both equal b37a945cc9b0020a3ca990ea27e4754e7865fe281bcfd23b82c237863778d955.
  - Immutable image sha256:cbaea887a917f23cbdf2aea4a8ad1486eb3763ea0c1d341ffc6f30d693790490 independently reports the exact F66 source hash.
  - The isolated F66 smoke executed both YOLO and Grounded-SAM on CUDA with QUALIFIED outcomes; no related container, process, or GPU task remained.
ruling: Repeat the exact frozen four-point two-Worker gate with F66 as the sole executable variable. Preserve every prior scheduling, perception, physical, recovery, visual, cleanup, model, image, config, and catalog criterion.
retained: all F66 build, test, scratch, provenance, image, smoke, and prior experiment evidence
archived: none
deletion_candidates: registered pytest/build scratch trees only; no deletion authorized
decision: RUN EXP-067 UNCHANGED FOUR-POINT GATE
```

## EXP-067 — F66 ordered readiness-request four-point gate

```yaml
experiment_id: EXP-067
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T02:43:29+08:00
  - status: RUNNING
    at: 2026-09-13T02:43:29+08:00
  - status: INVALID
    at: 2026-09-13T02:49:54+08:00
prior_experiment: EXP-066
hypothesis: Deferring ListControllers until all required service/action endpoints exist and retaining only one pending request will prevent the controller-manager service-response abort during parallel startup and recovery.
prediction: Four unique points finish PASSED with qualification_passed=true, every recovery receipt succeeds, cleanup-gates.json reports every component true, and no owned task remains.
single_variable: motion_stack_ready controller-state request ordering and single-pending-request discipline. All scheduling, worker identity, consumer readiness, perception, pose, motion, recovery, timeout, source/config/model/catalog, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f66
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f66
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recoveries and visuals pass, cleanup receipt entirely true, and no residual task.
provenance:
  executable_source_commit: 51baa98b6256c05c69c82208d926dfcce115f6b3
  executable_source_tree: e202be7120f08db46f1421ff5db1716d8a853dc3b9fdffa9017a0d1a9ab9f0ad
  installed_module_tree: b37a945cc9b0020a3ca990ea27e4754e7865fe281bcfd23b82c237863778d955
  image_id: sha256:cbaea887a917f23cbdf2aea4a8ad1486eb3763ea0c1d341ffc6f30d693790490
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp067.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f66 and root live-small-f66.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, recovery, visual, cleanup, or residual failure remains INVALID.
result: >-
  INVALID — exit 1 after 210.64 seconds solely at the cleanup qualification boundary. All four
  unique points PASSED; each Worker executed exactly two points; all four recovery receipts
  succeeded; and all eight original-resolution 640x480 RGB images passed. F66 eliminated the
  controller-manager response abort across initial startup and every recovery generation. All
  cleanup actions and process cleanup passed. Docker stop returned while the exact auto-remove
  container remained briefly inspectable, so the immediate post-stop inspect raised
  BROKER_CONTAINER_SURVIVED and coordinator completion was not attempted. Subsequent exact-ID
  readback proved the container absent, with no related process, GPU task, or domain claim.
retained: complete live-small-f66 tree, command-067 log/time/exit, visual report, root-cause report, cleanup audit, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-065
last_valid_experiment: EXP-022
current_hypothesis: Docker stop can return before a --rm Broker container disappears from inspect; bounded exact-ID absence polling after the already-validated stop will distinguish this removal lag from a surviving container without weakening ownership checks.
working_tree_status: clean executable source at 51baa98b6256c05c69c82208d926dfcce115f6b3; ledger-only EXP-067 closure pending bounded F67 TDD
owned_processes: NONE
confirmed_conclusions:
  - F66 is validated at its exact boundary: both Workers completed initial startup plus two recovery startups with no controller-manager RCLError or exit -6.
  - All four frozen points passed, both Workers respected K=2, all four recovery receipts succeeded, and all eight original-resolution RGB images passed.
  - Batch terminality was true before cleanup. Qualification remained false only because container_cleanup was false and coordinator completion correctly did not run.
  - Current retirement performs exactly one immediate inspect after docker stop. That inspect observed the auto-remove container before removal completed and raised BROKER_CONTAINER_SURVIVED; later exact-ID readback proved absence.
  - Exact pre-stop image, batch label, generation label, runtime mount, input mount, and full container ID validation already passed and must remain unchanged.
  - No process, container, GPU application, or domain claim remained after the run.
ruling: TDD one bounded F67 cleanup change. After exact ownership validation and docker stop, poll exact-ID inspect for absence within the existing heartbeat timeout; accept only proven absence, retain STOP_FAILED/SURVIVED fail-closed behavior at deadline, and never broaden container selection.
retained: EXP-067 runtime, visual, root-cause, cleanup, command, and all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: IMPLEMENT F67 BOUNDED AUTO-REMOVE OBSERVATION WITH TDD
```

```yaml
checkpoint_id: CP-066
last_valid_experiment: EXP-022
current_hypothesis: Bounded exact-ID polling after a validated Docker stop will absorb only the observed auto-remove lag and allow complete cleanup qualification without weakening Broker ownership or survival checks.
working_tree_status: clean executable source at 26f69805ff29c4cc3b4d7d70d142fba5bd2f2f44; F67 build, complete package, immutable-image, and dual-model CUDA smoke gates pass; this ledger update is the only pending tracked change
owned_processes: NONE
confirmed_conclusions:
  - F67 formal RED pytest-XZxTjFkA failed at the intended transient post-stop inspect boundary; focused GREEN passed twice with three selected tests.
  - The complete CLI gate passed 67 tests, the parallel suite passed 1045 tests, and the complete ordinary package gate passed 2796 tests with no errors, failures, or skips.
  - The complete source hash is 71106d326d45edb938743f6f2e4aff67dcaea2e05c211439c4924e72fc2a626d and source/install module hashes both equal cdd9e4635d58bb7625be6f9393da0aa5d5706eb048695dfceb3a63be2aa2b08d.
  - Immutable image sha256:7ef1b8fbe0fe1b62bccbae456b643f6473cb72c2670d51b9c94dfc4073dfdd01 independently reports the exact F67 source hash.
  - The isolated F67 smoke executed both YOLO and Grounded-SAM on CUDA with QUALIFIED outcomes; no related container, process, or GPU task remained.
  - Fresh preflight observed 24 CPUs, 24.407 GiB MemAvailable, 15272 MiB GPU free, no GPU applications or target container, and independently unlocked domains 181/182/183.
ruling: Repeat the exact frozen four-point two-Worker gate with F67 as the sole executable variable. Preserve every prior scheduling, perception, physical, recovery, visual, cleanup, model, image, config, and catalog criterion.
retained: all F67 build, test, scratch, provenance, image, smoke, and prior experiment evidence
archived: none
deletion_candidates: registered pytest/build scratch trees only; no deletion authorized
decision: RUN EXP-068 UNCHANGED FOUR-POINT GATE
```

## EXP-068 — F67 bounded Broker auto-remove four-point gate

```yaml
experiment_id: EXP-068
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T03:01:53+08:00
  - status: RUNNING
    at: 2026-09-13T03:02:54+08:00
  - status: INVALID
    at: 2026-09-13T03:08:54+08:00
prior_experiment: EXP-067
hypothesis: After exact Broker ownership validation and successful Docker stop, bounded polling of that exact container ID will observe auto-removal and allow the otherwise-complete four-point batch to qualify.
prediction: Four unique points finish PASSED with qualification_passed=true, every recovery receipt succeeds, cleanup-gates.json reports every component true, and no owned task remains.
single_variable: exact-ID post-stop absence polling within the existing heartbeat timeout. All scheduling, worker identity, consumer readiness, perception, pose, motion, recovery, timeout, source/config/model/catalog, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f67
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f67
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recoveries and visuals pass, cleanup receipt entirely true, and no residual task.
provenance:
  executable_source_commit: 26f69805ff29c4cc3b4d7d70d142fba5bd2f2f44
  executable_source_tree: 71106d326d45edb938743f6f2e4aff67dcaea2e05c211439c4924e72fc2a626d
  installed_module_tree: cdd9e4635d58bb7625be6f9393da0aa5d5706eb048695dfceb3a63be2aa2b08d
  image_id: sha256:7ef1b8fbe0fe1b62bccbae456b643f6473cb72c2670d51b9c94dfc4073dfdd01
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp068.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f67 and root live-small-f67.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, recovery, visual, cleanup, or residual failure remains INVALID.
result: >-
  INVALID — exit 1 after 182.28 seconds. task_start and cup_test_forward_5cm PASSED on
  worker-02; their four original-resolution RGB images passed visual inspection and both recovery
  receipts succeeded. worker-01 failed closed before authorization because its temporarily stable
  graph was missing /so101_base_to_camera_link; physical action was proven absent and recovery
  succeeded. That point was safely reissued and passed, but worker-02 then reached K=2 while
  worker-01 had stopped, so sample_05_near_center and sample_14_far_right remained UNRUN and the
  batch was nonterminal. The F67 boundary itself passed: all cleanup actions, process cleanup, and
  exact-ID container cleanup succeeded, and later readback found no related process, container,
  GPU task, or domain claim.
retained: complete live-small-f67 tree, command-068 log/time/exit, visual report, root-cause report, cleanup audit, MuJoCo log, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-067
last_valid_experiment: EXP-022
current_hypothesis: The initial-gate graph observer must wait within its existing timeout for the exact accepted Worker topology to become stable, not merely for any incomplete graph snapshot to repeat twice.
working_tree_status: clean executable source at 26f69805ff29c4cc3b4d7d70d142fba5bd2f2f44; EXP-068 closure is the only pending tracked change
owned_processes: NONE
confirmed_conclusions:
  - F67 passed its exact cleanup boundary: exact pre-stop ownership remained enforced, Docker stop succeeded, exact-ID removal was observed, and container_cleanup=true.
  - worker-01 observed a graph missing only /so101_base_to_camera_link at authorization time and correctly failed closed before physical action.
  - The same graph snapshot included all controller, MoveIt, MuJoCo, robot-state, camera-frame, and legitimate internal nodes, proving a startup visibility race rather than a stale-node admission.
  - worker-02 completed two unique points and both physical/visual results passed; all three recovery receipts succeeded.
  - Two points remained UNRUN because the only continuing Worker reached K=2; aggregate terminality and coordinator completion correctly remained false.
  - No related process, container, GPU application, or domain claim remained after exit.
ruling: TDD one bounded F68 observation change. Continue graph sampling only within the already-frozen initial-gate timeout until the exact accepted topology is present for stable samples; retain exact topology rejection, duplicate/unknown-node rejection, all other gate predicates, and fail-closed timeout behavior.
retained: EXP-068 runtime, visual, root-cause, cleanup, MuJoCo, command, and all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: IMPLEMENT F68 ACCEPTED-TOPOLOGY STABILITY WITH TDD
```

```yaml
checkpoint_id: CP-068
last_valid_experiment: EXP-022
current_hypothesis: Waiting for the exact accepted Worker topology to be present across stable graph samples will remove the transient missing-static-transform failure while preserving fail-closed node isolation.
working_tree_status: clean executable source at 7847bf280cf018a8515db8d1d1a67114976d21c0; F68 build, complete package, immutable-image, and dual-model CUDA smoke gates pass
owned_processes: NONE
confirmed_conclusions:
  - F68 RED pytest-TvsMIx5o reproduced premature return after two identical incomplete graph samples; focused GREEN returned the later complete topology.
  - Runtime/Worker adjacent tests passed 173, the full parallel suite passed 1045, and the complete ordinary package gate passed 2796 with no errors, failures, or skips.
  - The complete source hash is f0ac02faa60477a3132b5df5fab13dc5db7d78530218ce8168ad5bf5533ab1bf and source/install module hashes both equal 5e8da0702cbf3b83b649e1b79ad967dbb427926df76ecd6b7dda5c8bc9122e82.
  - Immutable image sha256:26e992ff4bf37be75f955279f41d20b1246fb59cfaa483d1ae5628bdf44382af reports the exact F68 source hash; both smoke models qualified on CUDA.
  - Fresh preflight observed 24 CPUs, 24.394 GiB MemAvailable, 15269 MiB GPU free, zero GPU applications or target containers, and unlocked domains 181/182/183.
ruling: Repeat the exact frozen four-point two-Worker gate with F68 as the sole executable variable. Preserve every prior scheduling, perception, physical, recovery, visual, cleanup, model, image, config, and catalog criterion.
retained: all F68 build, test, scratch, provenance, image, smoke, and prior experiment evidence
archived: none
deletion_candidates: registered pytest/build scratch trees only; no deletion authorized
decision: RUN EXP-069 UNCHANGED FOUR-POINT GATE
```

## EXP-069 — F68 stable accepted-topology four-point gate

```yaml
experiment_id: EXP-069
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T03:15:12+08:00
  - status: RUNNING
    at: 2026-09-13T03:15:12+08:00
  - status: VALID
    at: 2026-09-13T03:21:21+08:00
prior_experiment: EXP-068
hypothesis: Requiring the exact accepted Worker topology across stable graph samples before returning the point-initial observation will prevent transient missing-node invalidation and allow both Workers to consume the four-point queue.
prediction: Four unique points finish PASSED with qualification_passed=true, every recovery receipt succeeds, cleanup-gates.json reports every component true, and no owned task remains.
single_variable: initial-gate graph completion waits for the unchanged exact topology predicate within the unchanged timeout. All other scheduling, perception, motion, recovery, cleanup, model, config, catalog, and physical criteria remain frozen.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f68
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f68
success_criteria: Exit 0, POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, K<=2, all recoveries and visuals pass, cleanup receipt entirely true, and no residual task.
provenance:
  executable_source_commit: 7847bf280cf018a8515db8d1d1a67114976d21c0
  executable_source_tree: f0ac02faa60477a3132b5df5fab13dc5db7d78530218ce8168ad5bf5533ab1bf
  installed_module_tree: 5e8da0702cbf3b83b649e1b79ad967dbb427926df76ecd6b7dda5c8bc9122e82
  image_id: sha256:26e992ff4bf37be75f955279f41d20b1246fb59cfaa483d1ae5628bdf44382af
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight: reports/preflight-exp069.json
visual_method: Original-resolution immutable MuJoCo offscreen RGB for every authorized point, followed by complete per-image visual inspection.
command: The exact frozen four-point command under verified libexec PATH and full overlay, with batch parallel-small-20260913-v1-f68 and root live-small-f68.
acceptance: The complete frozen Task 14 live-small gate; any diagnostic, physical, recovery, visual, cleanup, or residual failure remains INVALID.
result: >-
  VALID — exit 0 after 209.03 seconds. All four unique points PASSED; worker-01 completed
  cup_test_forward_5cm and sample_14_far_right, worker-02 completed task_start and
  sample_05_near_center, and each stayed at K=2. All four recovery receipts succeeded. All four
  attempts used the YOLO-first model without fallback, and all eight original-resolution RGB
  images passed visual inspection. Numeric evidence showed upright table-supported cups, empty
  fingertip contacts and attachments, and complete retreat at every point. Aggregate terminality,
  cleanup, coordinator completion, and qualification were all true. Exact-ID container readback,
  owned-process manifests, GPU process readback, and domains 181/182/183 were clean after exit.
retained: complete live-small-f68 tree, command-069 log/time/exit, visual/result/cleanup reports, MuJoCo log, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-069
last_valid_experiment: EXP-069
current_hypothesis: The qualified F68 composition will preserve generation fencing, no-double-lease semantics, K accounting, and exact owned-process cleanup under controlled plan-only Worker and Broker termination.
working_tree_status: clean executable source at 7847bf280cf018a8515db8d1d1a67114976d21c0; EXP-069 closure is the only pending tracked change
owned_processes: NONE
confirmed_conclusions:
  - The frozen four-point execute gate is fully accepted with four PASSED points, four successful recoveries, eight passing original RGB inspections, and complete cleanup/qualification.
  - Dynamic queue assignment gave exactly two points to each Worker without duplicate valid leases or K overflow.
  - All four points used plastic-cup-yolo11n-seg-v1; Grounded-SAM fallback was not invoked.
  - F67 exact-ID Broker retirement and F68 accepted-topology stability both passed their live boundaries.
  - No process, container, GPU application, or ROS domain claim remained after the accepted batch.
ruling: Run controlled faults only in plan-only mode through scripts/inject_so101_parallel_fault.py against exact supervisor manifest identities. Never terminate a Worker during execute or use name-based process selection. Preserve source, install, image, config, catalog, models, N, K, and all safety timeouts.
retained: EXP-069 runtime, visual, result, cleanup, MuJoCo, command, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch trees only; no deletion authorized
decision: PREREGISTER CONTROLLED PLAN-ONLY FAULT GATES BEFORE FULL-20 ADMISSION
```

## EXP-070 — F68 controlled plan-only Worker and Broker termination

```yaml
experiment_id: EXP-070
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T03:22:47+08:00
  - status: RUNNING
    at: 2026-09-13T03:22:47+08:00
  - status: INVALID
    at: 2026-09-13T03:26:09+08:00
prior_experiment: EXP-069
hypothesis: Exact manifest-owned termination of one plan-only Worker followed by the current Broker will fence the old Worker/request authority, pause grants during Broker recovery without spending K, restart Broker generation g+1, allow the other Worker to continue, and leave no duplicate lease or owned process.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v1-f68
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f68
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
fault_sequence:
  - wait for worker-01 to own an attempt workspace, then invoke scripts/inject_so101_parallel_fault.py with the exact batch root, worker-01, TERM
  - re-read the manifest and invoke the same script against the exact current broker, TERM
success_criteria: Both injectors exit 0 after double identity readback; no execute action occurs; broker generation advances from 1 to 2; the non-target Worker continues; no old-generation result is admitted, no point has two simultaneous valid leases, K is not consumed by Broker pause, cleanup is conservative, and no owned process/container/GPU task/domain claim remains.
provenance:
  executable_source_commit: 7847bf280cf018a8515db8d1d1a67114976d21c0
  executable_source_tree: f0ac02faa60477a3132b5df5fab13dc5db7d78530218ce8168ad5bf5533ab1bf
  installed_module_tree: 5e8da0702cbf3b83b649e1b79ad967dbb427926df76ecd6b7dda5c8bc9122e82
  image_id: sha256:26e992ff4bf37be75f955279f41d20b1246fb59cfaa483d1ae5628bdf44382af
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
preflight_resources: 24 CPUs, 24.414 GiB MemAvailable, 15272 MiB GPU free, zero GPU applications/target containers, domains 181/182/183 unlocked
result: >-
  INVALID harness — no signal was injected. The readiness loop incorrectly watched execute-mode
  attempts/ paths while plan_only correctly created validations/ paths. Worker and Broker injector
  sentinels recorded 124 and 125 without invoking the script. The batch completed naturally in
  106.51 seconds; physical points remained UNRUN, all four validation outcomes were conservatively
  invalid, all cleanup components succeeded, and no related process, container, or GPU task remained.
retained: complete live-fault-f68 tree, command and injector sentinel reports, root-cause report, MuJoCo log, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-070
last_valid_experiment: EXP-069
current_hypothesis: Correctly observing the plan-only validations working path will provide a deterministic pre-seal injection window without changing the exact ownership or signal boundary.
working_tree_status: clean executable source at 7847bf280cf018a8515db8d1d1a67114976d21c0; EXP-070 closure and corrected EXP-071 registration are pending as ledger-only changes
owned_processes: NONE
confirmed_conclusions:
  - EXP-070 sent no signal and therefore says nothing about fault recovery; it is solely a harness-path failure.
  - Plan-only uses workers/<worker>/validations/<point>/<validation>/working, matching the frozen validation/physical artifact separation.
  - The no-signal batch still preserved physical UNRUN status and complete owned cleanup.
ruling: Repeat with the identical plan-only batch parameters under a fresh batch/root, changing only the readiness path from attempts to validations. Inject only after exact manifest and worker-01 validation working directory both exist.
retained: EXP-070 and all prior evidence
archived: none
deletion_candidates: none newly authorized
decision: RUN EXP-071 CORRECTED CONTROLLED PLAN-ONLY FAULT GATE
```

## EXP-071 — Corrected controlled plan-only Worker and Broker termination

```yaml
experiment_id: EXP-071
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T03:26:09+08:00
  - status: RUNNING
    at: 2026-09-13T03:26:09+08:00
  - status: INVALID
    at: 2026-09-13T03:35:58+08:00
prior_experiment: EXP-070
hypothesis: The corrected validation-workspace readiness check will permit exact manifest-owned Worker and Broker TERM injection and demonstrate the frozen fault properties.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v1-f68-r2
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f68-r2
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
single_harness_change: readiness watches worker-01/validations/*/*/working instead of attempts/*/*/working
success_criteria: Both exact injectors exit 0; physical points remain UNRUN; Broker generation advances; the non-target Worker continues; no duplicate valid lease or K debit during Broker pause; old authorities remain fenced; cleanup and residual audit pass.
provenance: identical to EXP-070 except docs-only runtime HEAD, batch ID, evidence root, and harness path
result: >-
  Both identity-checked injectors exited 0 and each sent one exact PGID TERM. Worker-01 was
  fenced and recovered with generation advancement, Worker-02 continued through two validation
  leases and generation 3, no physical action occurred, and final exact cleanup left no owned
  process, task container, GPU compute application, or ROS domain claim. The Broker fault criterion
  was not met: generation 2 was never created and the journal contains no BROKER_HEALTH_CHANGED
  event. Runtime timestamps prove the generation-1 Broker was model-ready five seconds before TERM.
  Its production docker command omitted --init, leaving Python as container PID 1; the proxied TERM
  did not terminate it, so the supervisor had no early exit from which to recover.
root_cause_report: reports/root-cause-EXP071.json
cleanup_audit: reports/post-071-cleanup-audit.json
retained: complete live-fault-f68-r2 tree, command/injector/MuJoCo/root-cause/cleanup reports, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-071
last_valid_experiment: EXP-069
current_hypothesis: Adding Docker --init to the immutable Broker launch command will make exact manifest-owned TERM observable by the supervisor, enabling bounded generation recovery without changing lease, K, timeout, or execution semantics.
working_tree_status: F69 RED/GREEN candidate changes only container_run_argv and its focused test; all EXP-071 runtime processes are stopped
owned_processes: NONE
confirmed_conclusions:
  - Worker termination fencing, replacement, non-target continuation, and physical UNRUN separation passed in EXP-071.
  - Broker TERM delivery passed exact identity checks but did not terminate the container PID-1 Python process.
  - EXP-071 is invalid for the combined fault gate because Broker generation did not advance.
ruling: Preserve all fault evidence, add a failing container argv contract for --init, implement only that signal-forwarding boundary, then rerun ordinary gates, the four-point execute gate, and controlled plan-only faults under fresh IDs.
retained: EXP-071 and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch trees only; no deletion authorized
decision: IMPLEMENT F69 CONTAINER INIT SIGNAL FORWARDING
```

## EXP-072 — F69 two-Worker four-point execute regression gate

```yaml
experiment_id: EXP-072
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T03:42:00+08:00
  - status: RUNNING
    at: 2026-09-13T03:42:00+08:00
  - status: VALID
    at: 2026-09-13T03:50:35+08:00
prior_experiment: EXP-071
hypothesis: The F69 Docker init boundary preserves the already-qualified four-point physical schedule, exact cleanup, visual outcomes, YOLO-first policy, and all Worker invariants before fault-gate repetition.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f69
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f69
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
success_criteria: Four distinct points PASSED in one batch; K=2 per Worker; all recoveries, original RGB inspections, terminal geometry, detach/retreat, cleanup, coordinator completion, qualification, exact container/GPU/process/domain residual checks pass; YOLO first and Grounded-SAM only as fallback.
provenance:
  executable_source_commit: 8462ea3ed5ac1efa8500604045659b9125fc2ee3
  executable_source_tree: ab94fcf022d60257514656dfde2a34a35fd4f0fe894d61f9490ee891cb1d7943
  installed_module_tree: f58ede82803183ca7ab5f56c187bdb83073aafe78b2a15cb671805f09144fb81
  image_id: sha256:c4f5d7bd655476800b035d6740d07f0e8bfa3a03528e7d68a622a22c45c12730
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
result: >-
  The F69 execute regression completed in 199.90 seconds with all four unique points PASSED,
  qualification and coordinator cleanup complete, exactly K=2 points per Worker, and all four
  Worker recoveries true. All eight original RGB images passed visual inspection; numeric terminal
  evidence showed upright table-supported cups, zero fingertip contacts, no attached object, and
  completed retreat. Every request selected plastic-cup-yolo11n-seg-v1 first with no fallback.
  Exact post-exit checks found no owned process, task container, GPU compute application, or ROS
  domain claim.
result_report: reports/result-EXP072.json
visual_report: reports/visual-inspection-EXP072.json
cleanup_audit: reports/post-072-cleanup-audit.json
retained: complete live-small-f69 tree, command/MuJoCo/result/visual/cleanup reports, F69 static gates, image build, smoke, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch trees only; no deletion authorized
```

```yaml
checkpoint_id: CP-072
last_valid_experiment: EXP-072
current_hypothesis: F69 will make exact Broker TERM observable, pause new leases without K debit, replace generation 1 with generation 2, and preserve Worker fencing and non-target progress in plan-only mode.
working_tree_status: clean executable source at 8462ea3ed5ac1efa8500604045659b9125fc2ee3; EXP-072 closure and EXP-073 registration are ledger-only
owned_processes: NONE
confirmed_conclusions:
  - The F69 source, overlay, immutable image, dual-model smoke, and four-point execute gates pass.
  - Four-point dynamic scheduling remains exactly K=2 per Worker with no duplicate point.
  - Visual, numeric, attachment, retreat, cleanup, and YOLO-first gates all pass.
ruling: Repeat the corrected combined controlled plan-only Worker and Broker TERM sequence under a fresh root; require a BROKER_HEALTH_CHANGED false/true pair and broker-g2 runtime identity before full-20 admission.
retained: EXP-072 and all prior evidence
archived: none
deletion_candidates: registered scratch trees only; no deletion authorized
decision: RUN EXP-073 F69 CONTROLLED PLAN-ONLY FAULT GATE
```

## EXP-073 — F69 controlled plan-only Worker and Broker termination

```yaml
experiment_id: EXP-073
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T03:51:30+08:00
  - status: RUNNING
    at: 2026-09-13T03:51:30+08:00
  - status: INVALID
    at: 2026-09-13T03:55:30+08:00
prior_experiment: EXP-072
hypothesis: Docker init makes exact Broker TERM observable and enables bounded generation-2 recovery while the already-proven Worker fault remains fenced and the non-target Worker continues without K over-debit.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v1-f69
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f69
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
fault_sequence:
  - wait for worker-01 validation working plus model-ready receipt, then inject exact manifest-owned worker-01 TERM
  - re-read the manifest and inject exact current Broker TERM
success_criteria: Both injectors exit 0; physical points remain UNRUN; journal records Broker unhealthy then healthy; broker generation advances 1 to 2; non-target Worker continues; old Worker/request authorities stay fenced; no duplicate valid lease or K debit during pause; cleanup and exact residual audit pass.
provenance: identical executable F69 source/install/image/config/catalog/model identities to EXP-072; distinct batch ID, evidence root, mode, and selection execution identity
result: >-
  Both exact injectors exited 0 and physical point statuses stayed UNRUN. Worker-01 termination
  disconnected an in-flight Broker RPC; generation 1 then crashed with an uncaught BrokenPipeError
  while sending the reply. The journal correctly recorded Broker unhealthy and the supervisor
  created generation 2. Because the harness waited only for the old Worker PID and not for Broker
  healthy/readiness, its explicit Broker injection then correctly targeted the current generation 2
  before it became ready. That invalidated the intended recovery observation. The batch nevertheless
  completed conservative cleanup with no task process, container, GPU application, or domain claim.
root_cause_report: reports/root-cause-EXP073.json
cleanup_audit: reports/post-073-cleanup-audit.json
retained: complete live-fault-f69 tree, command/injector/MuJoCo/root-cause/cleanup reports, and all prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-073
last_valid_experiment: EXP-072
current_hypothesis: Treating a disconnected Unix RPC client as a request-local failure will keep the shared Broker alive during Worker termination, so the subsequent exact Broker TERM can be isolated and its generation recovery observed.
working_tree_status: clean executable F69 source; EXP-073 closure is the only pending tracked change
owned_processes: NONE
confirmed_conclusions:
  - Docker --init made Broker process termination observable; generation 1 unhealthy state and generation 2 creation were recorded.
  - A Worker disconnect can currently kill the shared Broker through uncaught BrokenPipeError.
  - EXP-073 is invalid because the explicit Broker injection hit a replacement that was still starting.
ruling: Add a failing IPC test for reply-side BrokenPipeError, contain only client disconnect errors at the request boundary, rerun all source/image/small gates, then repeat the fault gate with explicit healthy-generation synchronization.
retained: EXP-073 and all prior evidence
archived: none
deletion_candidates: registered scratch trees only; no deletion authorized
decision: IMPLEMENT F70 REQUEST-LOCAL BROKEN-PIPE ISOLATION
```

## EXP-074 — F70 two-Worker four-point execute regression gate

```yaml
experiment_id: EXP-074
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T04:01:00+08:00
  - status: RUNNING
    at: 2026-09-13T04:01:00+08:00
  - status: VALID
    at: 2026-09-13T04:07:00+08:00
prior_experiment: EXP-073
hypothesis: Request-local disconnect containment preserves the complete two-Worker physical execution contract before another controlled fault run.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f70
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f70
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
success_criteria: Same complete physical, scheduling, visual, numeric, model, cleanup, qualification, and residual criteria as accepted EXP-072 under exact F70 provenance.
provenance:
  executable_source_commit: 86eaa5f7db650b914361cbadddb4a8041b56b87f
  executable_source_tree: 91e99d8d11302b3946b834834f3a1984c247fc2792e200e07a730f18c51e326a
  installed_module_tree: ff2679db7581928535b3b320539ea14e65d9deaea01ee379bee88c51e672c03d
  image_id: sha256:16fccaba3c3b679bf78858f1b9b5a15022bdbe0512133a6d1e7c0b00eb857bc7
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
result: F70 completed all four unique points PASSED in 197.42 seconds with qualification, K=2 scheduling, four recoveries, eight original RGB inspections, numeric detach/contact/upright/retreat gates, YOLO-first inference, coordinator completion, and exact residual cleanup all passing.
result_report: reports/result-EXP074.json
visual_report: reports/visual-inspection-EXP074.json
cleanup_audit: reports/post-074-cleanup-audit.json
retained: complete live-small-f70 tree and all command, MuJoCo, static, image, smoke, result, visual, cleanup, and prior evidence
archived: none
deletion_candidates: registered scratch trees only; no deletion authorized
```

## EXP-075 — F70 synchronized controlled plan-only fault gate

```yaml
experiment_id: EXP-075
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T04:07:00+08:00
  - status: RUNNING
    at: 2026-09-13T04:07:00+08:00
  - status: VALID
    at: 2026-09-13T04:13:26+08:00
prior_experiment: EXP-074
hypothesis: With reply disconnects contained, exact worker-01 TERM will not kill Broker g1; after Worker recovery is observed, exact Broker g1 TERM will pause grants and recover to a ready healthy g2 without K over-debit.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v1-f70
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f70
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
fault_sequence:
  - wait for Broker g1 ready and worker-01 validation working, inject exact worker-01 TERM
  - require Broker remains g1 and healthy while worker-01 advances generation, then inject exact Broker g1 TERM
  - require journal unhealthy/healthy transition and ready broker-g2 before judging
success_criteria: Exact injectors exit 0; all physical statuses UNRUN; old Worker/request fenced; non-target Worker continues; Broker g1 survives Worker disconnect, explicit g1 TERM leads to healthy ready g2; no double lease or K over-debit; cleanup/residual audit passes.
provenance: F70 source 86eaa5f7db650b914361cbadddb4a8041b56b87f, source tree 91e99d8d11302b3946b834834f3a1984c247fc2792e200e07a730f18c51e326a, image sha256:16fccaba3c3b679bf78858f1b9b5a15022bdbe0512133a6d1e7c0b00eb857bc7
result: >-
  Both exact TERM injectors exited 0. Worker-01 generation 1 was fenced and recovered while
  Broker generation 1 remained healthy. Exact Broker generation-1 termination then produced journal
  health transitions false at sequence 41 and true at sequence 63, followed by ready generation 2.
  No lease was granted inside that unhealthy window; each stable Worker slot received exactly two
  unique points despite reaching generation 3. All four physical statuses remained UNRUN, the
  non-target Worker continued, coordinator and batch cleanup completed, and the exact residual audit
  found no related process, container, GPU compute application, domain claim, or owned manifest entry.
result_report: reports/result-EXP075.json
cleanup_audit: reports/post-075-cleanup-audit.json
retained: complete live-fault-f70 tree and all command, injector, MuJoCo, result, cleanup, and prior evidence
archived: none
deletion_candidates: none from this experiment
```

```yaml
checkpoint_id: CP-075
last_valid_experiment: EXP-075
current_hypothesis: The unchanged qualified F70 executable and immutable runtime can complete every frozen catalog point once in one two-Worker batch while preserving K=10, isolation, recovery, evidence sealing, and cleanup invariants.
working_tree_status: clean executable F70 source at 86eaa5f7db650b914361cbadddb4a8041b56b87f; only this EXP-075 closure and EXP-076 preregistration are pending documentation changes
owned_processes: NONE
confirmed_conclusions:
  - The exact F70 package, parallel-suite, install, immutable-image, dual-model smoke, four-point execute, and synchronized fault gates are valid.
  - Worker termination is request-local to Broker; explicit Broker termination yields an observable unhealthy pause and ready replacement.
  - No lease is granted or K debited during the Broker unhealthy window; Worker generation changes do not reset K.
ruling: Admit one immutable full-catalog execute batch with two Workers and K=10. Source, install, config, catalog, models, and image remain byte-identical to EXP-074/075; only selection, N/K, batch ID, and evidence root change.
retained: EXP-075 and all prior evidence
archived: none
deletion_candidates: all registered pytest/build scratch trees; no deletion authorized
decision: RUN EXP-076 FULL 20-POINT QUALIFICATION
```

## EXP-076 — F70 immutable full 20-point qualification

```yaml
experiment_id: EXP-076
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T04:13:26+08:00
  - status: RUNNING
    at: 2026-09-13T04:13:26+08:00
  - status: INVALID
    at: 2026-09-13T04:30:57+08:00
prior_experiment: EXP-075
hypothesis: One immutable F70 batch will execute and seal all 20 frozen catalog points exactly once with dynamic two-Worker scheduling, K=10 per stable slot, YOLO-first perception, complete recovery, and no residual state.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-20-20260913-v1-f70
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f70
worker_count: 2
max_points_per_worker: 10
selection: complete frozen 20-point catalog; no --point-id filter
allowed_differences_from_exp074: complete selection instead of four-point selection; K=10 instead of K=2; batch ID and evidence root
preflight:
  related_processes: none
  containers: none
  gpu_compute_applications: none
  host_memory_available: 24 GiB
  gpu_memory_free: 15272 MiB
provenance:
  executable_source_commit: 86eaa5f7db650b914361cbadddb4a8041b56b87f
  executable_source_tree: 91e99d8d11302b3946b834834f3a1984c247fc2792e200e07a730f18c51e326a
  installed_module_tree: ff2679db7581928535b3b320539ea14e65d9deaea01ee379bee88c51e672c03d
  image_id: sha256:16fccaba3c3b679bf78858f1b9b5a15022bdbe0512133a6d1e7c0b00eb857bc7
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: 33374bb01c31f342e6a2f3d13943c91e74d62165a5a901678216bbb18ffa9a64
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: All 20 points have unique leases and sealed PASSED attempts in this batch; K=10 per Worker; coverage_complete, execution_complete, batch_cleanup_complete, and qualification_passed are true; every point passes initial, perception, planning/controller, final physical, attachment/contact/support/retreat, hash, and fresh visual gates; no residual owned state.
failure_rule: Any FAILED, INDETERMINATE, UNRUN, INVALID, duplicate/missing point, K violation, evidence/hash mismatch, cleanup failure, or qualification false makes this batch non-qualifying; after a required fix, rerun all 20 points under a new batch ID.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: >-
  The immutable batch exited 1 after 338.49 seconds with truthful CAPACITY_EXHAUSTED.
  task_start and the three cup-test points completed PASSED. After Worker-02 completed its second
  point and recovered to generation 3, the next model request returned INFRA_ERROR/BROKER_NOT_READY;
  Worker-01 then observed the same state. The container and immutable health receipt stayed live, so
  the supervisor did not pause leases or replace the internally unhealthy Broker. Each Worker
  conservatively sealed eight INVALID attempts without physical action and stopped at K=10, leaving
  16 points UNRUN. execution_complete and batch_cleanup_complete are true; coverage_complete and
  qualification_passed are false. No related process, container, GPU application, or owned manifest
  entry remained.
diagnosis: >-
  The failed sample_01 RGB independently qualified both models in the same immutable image. Its exact
  NPY also qualified through the same ParallelPerceptionRuntime after restoring the required pre-seal
  0400 mode. The current runtime health callback overwrites the initiating infrastructure response
  with generic BROKER_NOT_READY before the Worker can retain the specific reason, so the next fix is
  diagnostic preservation, not a threshold or perception-policy change.
result_report: reports/result-EXP076.json
root_cause_report: reports/root-cause-EXP076.json
cleanup_audit: reports/post-076-cleanup-audit.json
retained: complete live-20-f70 tree; command, MuJoCo, result, root-cause, cleanup, and isolated image/runtime diagnostic evidence; all prior evidence
archived: none
deletion_candidates: diagnosis scratch-style runtime copies and all previously registered pytest/build scratch trees; no deletion authorized
```

```yaml
checkpoint_id: CP-076
last_valid_experiment: EXP-075
current_hypothesis: Preserving the first model-runtime infrastructure reason before publishing irreversible unhealthy state will expose the initiating F70 fault without weakening fail-closed Broker behavior.
working_tree_status: clean at preregistration commit c474b1f6d; EXP-076 closure is the only pending tracked change
owned_processes: NONE
confirmed_conclusions:
  - EXP-076 is non-qualifying at 4 PASSED, 16 UNRUN, 16 INVALID attempts, and exact K=10 per Worker.
  - The frozen image and failed point input are independently healthy; the generic BROKER_NOT_READY cascade is not a deterministic detection rejection.
  - Internal Broker unhealthy state is not surfaced through process liveness, allowing invalid retries to consume capacity, contrary to the shared-dependency pause intent.
ruling: Add a focused RED test that requires the first infrastructure reason to survive health fanout, make the smallest ordering correction, rerun focused/adjacent/full package gates, rebuild overlay and immutable image, then use a fresh live gate to obtain the actionable initiating reason before another full-catalog run.
retained: EXP-076 and all prior evidence
archived: none
deletion_candidates: diagnosis runtime copies plus registered pytest/build scratch trees; no deletion authorized
decision: IMPLEMENT F71 FIRST-INFRASTRUCTURE-REASON PRESERVATION
```

```yaml
fix_id: F71
status: VALIDATED_STATIC
source_commit: 3b5e5ac8cc0ac587319eed77003ebb40efa534ca
change: Defer runtime health fanout until PerceptionService has committed the initiating request's exact infrastructure result; retain irreversible unhealthy behavior afterward.
formal_red: pytest-jUOP91By, 1 failed because diagnostic CUDA sentinel was overwritten by BROKER_NOT_READY
focused_green: pytest-G3PLXuNz, 1 passed
adjacent_green: pytest-UAnEWLQk, 328 passed
parallel_suite: pytest-oFxQIIMr, 1082 passed in 42.34 seconds
ordinary_package_gate: pytest-TV4cUG2H, 2798 passed and 4 warnings in 82.94 seconds
invalid_harness_attempt: pytest-XQglRfDK omitted the full worktree message overlay and is retained but excluded from product judgment
build: p106 passed in 1.50 seconds; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p106-cq9ly6KN/tmp
source_tree_sha256: 1014ac5c014dc3f88876709d893dc6e826b476a3817726e7d94d1c67a196e36d
module_tree_sha256: 4260fb551f30275f621916d8a1f891b2a4175768efdb658f4aa5e7e17974c316
image_id: sha256:0d2307e52e470a0461c2f383009c086fe2c0a3cc10b1220c8864e0686e91a776
image_build: p107 passed in 12.53 seconds; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p107-kgWcrDgn/tmp
smoke: task14-f71-smoke qualified YOLO and Grounded-SAM on CUDA using the EXP-076 sample_01 frame; 32.603054 ms and 195.761351 ms respectively; container auto-removed
static_report: reports/f71-static-gates.json
installed_provenance: reports/installed-provenance-f71.json
retained: source/tests, all RED/GREEN/package/build/image/smoke evidence, invalid harness evidence, and prior evidence
archived: none
deletion_candidates: registered pytest/build scratch and diagnosis runtime copies; no deletion authorized
```

## EXP-077 — F71 six-point plan-only Broker diagnosis

```yaml
experiment_id: EXP-077
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T04:37:50+08:00
  - status: RUNNING
    at: 2026-09-13T04:37:50+08:00
  - status: INVALID
    at: 2026-09-13T04:40:44+08:00
prior_experiment: EXP-076
hypothesis: Repeating three perception/planning cycles per Worker without physical action will either remain healthy or retain the exact initiating reason at the first post-recovery Broker infrastructure failure instead of a generic cascade.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-diagnostic-plan-20260913-v1-f71
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-diagnostic-f71
worker_count: 2
max_points_per_worker: 3
selection: task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm, sample_01_near_left, sample_02_near_center
selection_sha256: 2c4052ef4c72a434f7a57b1e075b02d517250c0130c7014ff60443203b0a318a
provenance: F71 source 3b5e5ac8cc0ac587319eed77003ebb40efa534ca, source tree 1014ac5c014dc3f88876709d893dc6e826b476a3817726e7d94d1c67a196e36d, image sha256:0d2307e52e470a0461c2f383009c086fe2c0a3cc10b1220c8864e0686e91a776
success_criteria: All six validation outcomes are terminal and uniquely leased at K=3 per Worker; physical statuses stay UNRUN; any infrastructure failure retains its initiating reason; recovery, cleanup, and exact residual audit pass.
retention_rule: Retain all evidence; delete nothing without explicit authorization.
result: >-
  The batch exited 1 after 115.74 seconds with all six unique points terminal as
  VALIDATION_INVALID at the admit_pose boundary. Each Worker received exactly three leases and
  recovered through generation 4; every physical point status remained UNRUN. The exact failure was
  POSE_ACCEPTED_PUBLICATION_FAILED, because plan_only has no consumer for the pose-accepted
  publication. The batch therefore never exercised the intended post-recovery Broker inference
  boundary and is invalid as an F71 diagnostic, without constituting a product regression finding.
  Cleanup was complete with no related process, container, GPU application, or owned manifest entry.
result_report: reports/result-EXP077.json
cleanup_audit: reports/post-077-cleanup-audit.json
retained: complete live-diagnostic-f71 tree, command and MuJoCo logs, result and cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, diagnosis runtime copies, and the invalid diagnostic batch; no deletion authorized
```

```yaml
checkpoint_id: CP-077
last_valid_experiment: EXP-075
current_hypothesis: A six-point execute batch is the smallest live gate that reaches three complete perception/recovery cycles per Worker and can reveal F71's preserved initiating Broker reason without the plan_only publication artifact.
working_tree_status: clean at F71 preregistration commit e669930986021c35aaa3d7cdb07b6c554b99a3a6; this EXP-077 closure and EXP-078 preregistration are the only pending tracked changes
owned_processes: NONE
confirmed_conclusions:
  - EXP-077 is invalid as a Broker diagnostic because plan_only stops at POSE_ACCEPTED_PUBLICATION_FAILED before the target post-recovery inference boundary.
  - Its six unique leases, exact K=3 per Worker, recovery receipts, physical UNRUN status, and clean teardown remain valid audit evidence.
  - No F71 product conclusion is drawn from EXP-077.
ruling: Run the same frozen six-point selection in execute simulation mode under a new batch ID and evidence root; inspect every original RGB if the batch reaches physical execution.
retained: EXP-077 and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, diagnosis runtime copies, and invalid diagnostic evidence; no deletion authorized
decision: RUN EXP-078 SIX-POINT EXECUTE DIAGNOSTIC
```

## EXP-078 — F71 six-point execute Broker diagnostic

```yaml
experiment_id: EXP-078
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T04:42:26+08:00
  - status: RUNNING
    at: 2026-09-13T04:43:35+08:00
  - status: INVALID
    at: 2026-09-13T04:47:51+08:00
prior_experiment: EXP-077
hypothesis: Three complete execute/recovery cycles per Worker will either remain healthy or retain the exact initiating reason at the first post-recovery Broker infrastructure failure instead of a generic BROKER_NOT_READY cascade.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-diagnostic-execute-20260913-v1-f71
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-diagnostic-execute-f71
worker_count: 2
max_points_per_worker: 3
selection: task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm, sample_01_near_left, sample_02_near_center
selection_sha256: 2c4052ef4c72a434f7a57b1e075b02d517250c0130c7014ff60443203b0a318a
provenance:
  executable_source_commit: 3b5e5ac8cc0ac587319eed77003ebb40efa534ca
  preregistration_commit: 49407b9bf5f6697d74922e9660df5205a2655dd7
  executable_source_tree: 1014ac5c014dc3f88876709d893dc6e826b476a3817726e7d94d1c67a196e36d
  installed_module_tree: 4260fb551f30275f621916d8a1f891b2a4175768efdb658f4aa5e7e17974c316
  image_id: sha256:0d2307e52e470a0461c2f383009c086fe2c0a3cc10b1220c8864e0686e91a776
success_criteria: All six unique points have sealed PASSED attempts; each Worker receives exactly three leases; all 12 original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, provenance, hash, and cleanup gates pass; any infrastructure failure retains its exact initiating reason; execution_complete, batch_cleanup_complete, coverage_complete, and qualification_passed are true; no residual owned state remains.
failure_rule: Any FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, cleanup failure, or qualification false makes this batch non-qualifying and requires diagnosis before another full-catalog run.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: >-
  The batch exited 1 after 255.91 seconds with five unique points PASSED and
  sample_02_near_center UNRUN. Broker health remained true and no model or Broker failure occurred.
  Worker-01's generation-3 ros2_control_node aborted with exit -6 during recovery startup after an
  orphaned controller-manager service response threw rclcpp::exceptions::RCLError through the
  executor top level. Worker-01's second recovery receipt was false, leaving lease counts 2 and 3;
  the coordinator truthfully terminated CAPACITY_EXHAUSTED. execution_complete and
  batch_cleanup_complete are true; coverage_complete and qualification_passed are false. No process,
  container, GPU application, or owned manifest entry remained.
result_report: reports/result-EXP078.json
root_cause_report: reports/root-cause-EXP078.json
cleanup_audit: reports/post-078-cleanup-audit.json
retained: complete live-diagnostic-execute-f71 tree, command and MuJoCo logs, result, root-cause and cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
```

```yaml
checkpoint_id: CP-078
last_valid_experiment: EXP-075
current_hypothesis: Treating a disconnected-client send_response RCLError as a request-local executor event will preserve the healthy controller process and allow every Worker recovery generation to complete.
working_tree_status: clean at F72 source commit ba55e038dfa7b8e3f3edcdcca119066b3b237afa
owned_processes: NONE
confirmed_conclusions:
  - EXP-078 proves F71 did not encounter the prior Broker failure: five physical points passed and Broker health remained true throughout.
  - The only lost point came from an uncaught controller-manager send_response RCLError during Worker-01 recovery startup; its exact launch log and failed recovery receipt are retained.
  - The response target had disappeared, so the failure is request-local; unrelated rclcpp exceptions must remain fatal.
ruling: Add a narrowly classified executor boundary that logs and continues only for the exact disconnected-response error, rethrowing every other RCLError; compile and test the controller package before a fresh six-point execute rerun.
retained: EXP-078 and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, diagnosis runtime copies, and invalid diagnostic evidence; no deletion authorized
decision: IMPLEMENT AND VALIDATE F72
```

```yaml
fix_id: F72
status: VALIDATED_STATIC
source_commit: ba55e038dfa7b8e3f3edcdcca119066b3b237afa
submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
change: Keep ros2_control_node alive when ControllerManager cannot send a response to a disconnected service client; emit MUJOCO_ROS2_CONTROL_DROPPED_SERVICE_RESPONSE and rethrow every unrelated rclcpp::exceptions::RCLError.
formal_red: pytest-KfU5I8p7, 1 failed because the resilient executor boundary was absent
invalid_adjacent_harness: pytest-A5TKoGzO omitted the full worktree message overlay and produced 3 unrelated ImportErrors; retained and excluded from product judgment
focused_green: pytest-HEESdNSA, 1 passed
adjacent_green: pytest-FTvRR6yO, 12 passed and 3 platform skips in 0.32 seconds
build: p108 passed in 7.98 seconds; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p108-fximheOJ/tmp
package_gate: p109 colcon test passed all 10 test targets in 7.63 seconds and 8.03 seconds wall; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p109-LrRFPWD4/tmp
installed_binary_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
read_only_uncrustify: reports/f72-uncrustify.log records repository-baseline whole-file divergence; no automatic reformat was performed and the targeted patch follows the file's existing brace style
retained: source/tests, RED/GREEN/build/package evidence, invalid harness evidence, EXP-078, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch and prior diagnosis runtime copies; no deletion authorized
```

## EXP-079 — F72 six-point execute recovery regression

```yaml
experiment_id: EXP-079
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T04:54:00+08:00
  - status: RUNNING
    at: 2026-09-13T04:55:16+08:00
  - status: INVALID
    at: 2026-09-13T04:58:01+08:00
prior_experiment: EXP-078
hypothesis: The F72 request-local executor boundary prevents the observed recovery-generation controller abort, allowing three complete execute/recovery cycles per Worker while leaving all unrelated controller exceptions fail-fast.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-diagnostic-execute-20260913-v2-f72
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-diagnostic-execute-f72
worker_count: 2
max_points_per_worker: 3
selection: task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm, sample_01_near_left, sample_02_near_center
selection_sha256: 2c4052ef4c72a434f7a57b1e075b02d517250c0130c7014ff60443203b0a318a
provenance:
  executable_source_commit: ba55e038dfa7b8e3f3edcdcca119066b3b237afa
  preregistration_commit: 93a0d90d87ff3907804fc0c0afc63b727083468c
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image_id: sha256:0d2307e52e470a0461c2f383009c086fe2c0a3cc10b1220c8864e0686e91a776
success_criteria: All six unique points have sealed PASSED attempts; each Worker receives exactly three leases and completes recovery through generation 4; all 12 original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, provenance, hash, and cleanup gates pass; execution_complete, batch_cleanup_complete, coverage_complete, and qualification_passed are true; no residual owned state remains.
failure_rule: Any FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, recovery or cleanup failure, or qualification false makes this batch non-qualifying and requires diagnosis before any full-catalog run.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: >-
  The batch exited 1 after 141.62 seconds with cup_test_forward_5cm PASSED and the other
  five points UNRUN. Both Workers consumed exactly K=3 leases; five attempts stopped at the
  dynamic consumer's five-second CUP_POSE_TIMEOUT with physical action proven absent. All six
  recovery receipts succeeded, no ros2_control_node aborted, and Broker health remained true,
  confirming F72 fixed the EXP-078 controller failure. The coordinator truthfully terminated
  CAPACITY_EXHAUSTED; execution_complete and batch_cleanup_complete are true while coverage_complete
  and qualification_passed are false. No related process, container, GPU application, or owned
  manifest entry remained.
diagnosis: >-
  The publisher observed exactly one matched dynamic consumer before each one-shot /cup_pose
  publication, but RosCupPoseSource requested BEST_EFFORT while the default publisher offered
  RELIABLE. The one successful point establishes intermittent one-shot loss, not deterministic pose
  rejection. The control message must use RELIABLE while retaining VOLATILE durability so stale poses
  cannot cross recovery generations.
result_report: reports/result-EXP079.json
root_cause_report: reports/root-cause-EXP079.json
cleanup_audit: reports/post-079-cleanup-audit.json
retained: complete live-diagnostic-execute-f72 tree, command and MuJoCo logs, result, root-cause and cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
```

```yaml
checkpoint_id: CP-079
last_valid_experiment: EXP-075
current_hypothesis: RELIABLE plus VOLATILE subscriber QoS will make every matched one-shot /cup_pose control publication deterministic across fresh Worker recovery generations without admitting stale poses.
working_tree_status: clean at F73 source commit 8d2a3f367119936f88b551dfd96462c2423bcaad
owned_processes: NONE
confirmed_conclusions:
  - F72 is live-validated at its target boundary: all six recoveries succeeded and no controller process crashed.
  - EXP-079 is non-qualifying at one PASSED point, five UNRUN points, five validation-invalid attempts, and exact K=3 per Worker.
  - Every invalid attempt stopped before physical action; Broker, teardown, and residual-state gates passed.
ruling: Require RELIABLE and VOLATILE QoS for RosCupPoseSource, rerun focused/adjacent/full package gates, rebuild the overlay and immutable image, then rerun the six-point execute regression before the small, synchronized-fault, and full-catalog gates.
retained: EXP-079, F73 test/build evidence, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, diagnosis runtime copies, and invalid diagnostic evidence; no deletion authorized
decision: BUILD AND QUALIFY F73 IMMUTABLE IMAGE
```

```yaml
fix_id: F73
status: VALIDATED_STATIC
source_commit: 8d2a3f367119936f88b551dfd96462c2423bcaad
submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
change: Use RELIABLE and VOLATILE QoS for the one-shot dynamic cup-pose control message and update both dependency locks to the F72 mujoco_ros2_control revision.
formal_red: pytest-RHtn57Jm, 1 failed because RosCupPoseSource requested BEST_EFFORT
focused_green: pytest-DEH5493v, 4 passed
adjacent_green: pytest-qUDLr2fW, 78 passed
parallel_suite: pytest-CwyYVdSd, 1047 passed in 41.94 seconds
invalid_ordinary_harness: pytest-Wigg3yCC omitted the test-only locked ML path and is retained but excluded from product judgment
pre_lock_ordinary_gate: pytest-KfVH56pT, 2798 passed and 1 lock-revision failure that directly prompted the lock update
lock_gate: pytest-Oi9Vj0Qf, 18 passed
ordinary_package_gate: pytest-5EalFt4b, 2799 passed and 4 warnings in 81.56 seconds
build: p110 passed in 1.53 seconds; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p110-ZnYCgLla/tmp
backend_integration: passed
source_tree_sha256: 4d68c3518a542ab3353981d89e92c077be9ec512cde60f58323f78938f2480f1
module_tree_sha256: 819a372e4b280fdc0e12756ba0fe49a3b1310afc522f25b2cd4ce162dd59be25
dependency_lock_sha256: 84557a10b2d42141ba8875921f4ca7ab1926efeab1a0adb3e85c1ffe5966a5a4
mujoco_dependency_lock_sha256: 80cb5d2641a95619da6d6fbdf993e973c02914c9bb9213620ef0abc07d4a39ca
installed_controller_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
image_id: sha256:81b287d4fc8645615cc8f5622ec9b687577eda6ce2446c08e59a15aacd5dba7f
image_build: p111 passed in 12.55 seconds; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p111-toOiHN1c/tmp; source and independently verified source both 4d68c3518a542ab3353981d89e92c077be9ec512cde60f58323f78938f2480f1
invalid_smoke_attempt: task14-f73-smoke failed before batch creation because the required batch root was absent; no container or GPU inference started; retained and excluded from product judgment
smoke: task14-f73-smoke-v2 qualified YOLO and Grounded-SAM on CUDA using the EXP-076 sample_01 frame; 31.697368 ms and 187.294990 ms respectively; immutable provenance matched and container/GPU cleanup was clean
static_report: reports/f73-static-gates.json
installed_provenance: reports/installed-provenance-f73.json
retained: source/tests, all RED/GREEN/package/build/integration evidence, invalid harness evidence, EXP-079, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch and prior diagnosis runtime copies; no deletion authorized
```

## EXP-080 — F73 six-point execute delivery and recovery regression

```yaml
experiment_id: EXP-080
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:12:26+08:00
  - status: RUNNING
    at: 2026-09-13T05:13:08+08:00
  - status: INVALID
    at: 2026-09-13T05:16:51+08:00
prior_experiment: EXP-079
hypothesis: RELIABLE plus VOLATILE subscriber QoS delivers every matched one-shot /cup_pose message across three fresh execute/recovery cycles per Worker while F72 keeps each controller generation healthy.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-diagnostic-execute-20260913-v3-f73
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-diagnostic-execute-f73
worker_count: 2
max_points_per_worker: 3
selection: task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm, sample_01_near_left, sample_02_near_center
selection_sha256: 2c4052ef4c72a434f7a57b1e075b02d517250c0130c7014ff60443203b0a318a
provenance:
  executable_source_commit: 8d2a3f367119936f88b551dfd96462c2423bcaad
  preregistration_commit: 31e5e1f99c8b60f27bc42105a8981859763f67df
  executable_source_tree: 4d68c3518a542ab3353981d89e92c077be9ec512cde60f58323f78938f2480f1
  installed_module_tree: 819a372e4b280fdc0e12756ba0fe49a3b1310afc522f25b2cd4ce162dd59be25
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image_id: sha256:81b287d4fc8645615cc8f5622ec9b687577eda6ce2446c08e59a15aacd5dba7f
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: All six unique points have sealed PASSED attempts; each Worker receives exactly three leases and completes recovery through generation 4; all 12 original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, provenance, hash, and cleanup gates pass; no CUP_POSE_TIMEOUT or controller abort occurs; execution_complete, batch_cleanup_complete, coverage_complete, validation_complete, validation_passed, and qualification_passed are true; no residual owned state remains.
failure_rule: Any FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, recovery or cleanup failure, or qualification false makes this batch non-qualifying and requires diagnosis before the small, synchronized-fault, or full-catalog gates.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: >-
  The batch exited 1 after 162.76 seconds with cup_test_forward_5cm PASSED and five
  points UNRUN. Both Workers consumed exactly K=3 leases, all six recoveries succeeded, Broker
  process health remained true, and no controller aborted. The initiating task_start attempt failed
  before physical action because its exact-stamp lookup allowed only 0.2 seconds and the fresh TF
  listener had not yet discovered the world frame. Cancellation conservatively made the internal
  Broker unavailable, so four subsequent attempts returned BROKER_NOT_READY; their five child-side
  CUP_POSE_TIMEOUT messages are downstream because no admitted pose was published. execution_complete
  and batch_cleanup_complete are true while coverage_complete and qualification_passed are false.
  No related process, container, GPU application, or owned manifest entry remained.
diagnosis: >-
  The F73 control-message path completed successfully for cup_test_forward_5cm. EXP-080 instead
  exposed a distinct fresh-stack TF discovery race: RGB-D capture can precede availability of the
  exact world-to-camera transform, and the hard-coded 0.2-second lookup window is shorter than the
  existing point-stage budget. F74 must add a bounded exact-transform readiness window while
  preserving exact timestamp lookup and fail-closed behavior.
result_report: reports/result-EXP080.json
root_cause_report: reports/root-cause-EXP080.json
cleanup_audit: reports/post-080-cleanup-audit.json
retained: complete live-diagnostic-execute-f73 tree, command log, result, root-cause and cleanup reports, F73 image/smoke evidence, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke command evidence, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
```

```yaml
checkpoint_id: CP-080
last_valid_experiment: EXP-075
current_hypothesis: A bounded exact-transform readiness window within the existing point-stage deadline will absorb fresh TF discovery latency without relaxing exact-stamp or provenance checks.
working_tree_status: clean at EXP-080 running commit 9f5ed99def0d17dfe7ef7c45d7dd6b2c5091e8e6; this closure is the only pending tracked change
owned_processes: NONE
confirmed_conclusions:
  - F73 delivered one admitted pose through the live RELIABLE/VOLATILE path and that point PASSED; no F73 delivery failure initiated this batch.
  - The exact initiating error was TF_UNAVAILABLE because the fresh listener did not yet know target frame world within 0.2 seconds.
  - Four BROKER_NOT_READY results and five child CUP_POSE_TIMEOUT messages were downstream of that initiating failure, not independent causes.
  - All invalid attempts stopped before physical action; all six recovery and final residual-state gates passed.
ruling: Add a focused RED contract for a bounded longer exact-transform lookup, replace the hard-coded 0.2-second window with the smallest safe constant under the existing stage deadline, rerun static gates/build/image/smoke, then repeat the six-point regression under a new immutable batch identity.
retained: EXP-080 and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke command evidence, diagnosis runtime copies, and invalid diagnostic evidence; no deletion authorized
decision: IMPLEMENT F74 EXACT-TF READINESS WINDOW
```

```yaml
fix_id: F74
status: VALIDATED_STATIC
source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
change: Allow up to five seconds for fresh exact-stamp TF discovery while preserving exact timestamp lookup and fail-closed timeout behavior.
invalid_test_attempts: pytest-IZkbmb8W used an invalid request fixture and pytest-qzJcNDXi asserted a nonexistent LocalizedPose field; both are retained and excluded from product judgment
formal_red: pytest-1kvdCJGf, 1 failed because production supplied 0.2 seconds instead of the required 5.0 seconds
focused_green: pytest-MFrd1vnd, 1 passed
adjacent_green: pytest-nCQXXDQc, 24 passed
parallel_suite: pytest-JAhNVTb7, 1048 passed in 41.81 seconds
ordinary_package_gate: pytest-yiqZn26V, 2800 passed and 4 warnings in 81.59 seconds
build: p112 passed in 1.54 seconds; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p112-dufaASGh/tmp
backend_integration: passed
source_tree_sha256: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
module_tree_sha256: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
image_build: p113 passed in 11.63 seconds; scratch /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p113-ZqjKjNdH/tmp; source and independently verified source both 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
smoke: task14-f74-smoke qualified YOLO and Grounded-SAM on CUDA using the EXP-076 sample_01 frame; 34.534182 ms and 191.216042 ms respectively; immutable provenance matched and container/GPU cleanup was clean
static_report: reports/f74-static-gates.json
installed_provenance: reports/installed-provenance-f74.json
retained: source/tests, all RED/GREEN/package/build/image/smoke evidence, invalid test evidence, EXP-080, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke command evidence, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
```

## EXP-081 — F74 six-point exact-TF, delivery, and recovery regression

```yaml
experiment_id: EXP-081
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:26:17+08:00
  - status: RUNNING
    at: 2026-09-13T05:26:46+08:00
  - status: INVALID
    at: 2026-09-13T05:31:45+08:00
prior_experiment: EXP-080
hypothesis: The F74 five-second exact-stamp TF discovery window removes the fresh-stack localization race, allowing F73 pose delivery and F72 controller recovery to complete three execute cycles per Worker.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-diagnostic-execute-20260913-v4-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-diagnostic-execute-f74
worker_count: 2
max_points_per_worker: 3
selection: task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm, sample_01_near_left, sample_02_near_center
selection_sha256: 2c4052ef4c72a434f7a57b1e075b02d517250c0130c7014ff60443203b0a318a
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: 83bdce7d97a1dd18b6046a222ba1fae7e4a63f13
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: All six unique points have sealed PASSED attempts; each Worker receives exactly three leases and completes recovery through generation 4; all 12 original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, provenance, hash, and cleanup gates pass; no initiating TF_UNAVAILABLE, CUP_POSE_TIMEOUT, BROKER_NOT_READY, or controller abort occurs; execution_complete, batch_cleanup_complete, coverage_complete, validation_complete, validation_passed, and qualification_passed are true; no residual owned state remains.
failure_rule: Any FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, recovery or cleanup failure, or qualification false makes this batch non-qualifying and requires diagnosis before the small, synchronized-fault, or full-catalog gates.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: >-
  The product batch exited 0 after 271.03 seconds with all six unique points PASSED, exact K=3
  per Worker, recovery through generation 4, Broker health true, POINTS_COMPLETE, complete execution,
  coverage, qualification, cleanup, manifest hashes, numeric/dynamic evidence, and 12 accepted
  original-resolution RGB images. No target runtime fault or residual owned state occurred. The
  experiment is nevertheless INVALID because its preregistered acceptance mistakenly required
  validation_complete and validation_passed to be true in execute mode; those fields are correctly
  false and inapplicable while qualification_passed is true. No product failure is inferred.
result_report: reports/result-EXP081.json
visual_review: reports/visual-review-EXP081.json
cleanup_audit: reports/post-081-cleanup-audit.json
retained: complete live-diagnostic-execute-f74 tree, command and MuJoCo logs, result, visual review and cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke command evidence, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
```

```yaml
checkpoint_id: CP-081
last_valid_experiment: EXP-075
current_hypothesis: F74, F73, and F72 jointly satisfy the six-point runtime target; repeating the identical batch under an execute-correct acceptance contract will make that evidence formally admissible.
working_tree_status: clean at EXP-081 running commit 9fe841410490b4f875d7ee02716a410361d4c3d0; this closure is the only pending tracked change
owned_processes: NONE
confirmed_conclusions:
  - All six product points PASSED with exact K=3, generation 4, complete recovery, immutable provenance, and clean teardown.
  - All 12 original RGB images passed fresh original-resolution inspection and all sealed file hashes matched.
  - Execute mode correctly leaves validation_complete and validation_passed false; qualification_passed is the applicable terminal gate.
ruling: Preserve EXP-081 as invalid acceptance-authoring evidence, preregister the identical F74 six-point run without the inapplicable validation fields, and rerun under a new batch ID and root before advancing.
retained: EXP-081 and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke command evidence, diagnosis runtime copies, and invalid diagnostic evidence; no deletion authorized
decision: RERUN SIX-POINT F74 AS EXP-082
```

## EXP-082 — F74 admissible six-point execute regression

```yaml
experiment_id: EXP-082
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:34:08+08:00
  - status: RUNNING
    at: 2026-09-13T05:34:41+08:00
  - status: INVALID
    at: 2026-09-13T05:35:10+08:00
prior_experiment: EXP-081
hypothesis: Repeating the identical F74 runtime under an execute-correct acceptance contract will reproduce all six PASSED points, exact recovery, and fresh visual acceptance without the EXP-081 preregistration defect.
single_variable: Acceptance contract removes only validation_complete and validation_passed, which are inapplicable to execute mode; source, install, image, models, config, catalog, selection, N=2, K=3, and runtime behavior remain fixed.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-diagnostic-execute-20260913-v5-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-diagnostic-execute-f74-v2
worker_count: 2
max_points_per_worker: 3
selection: task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm, sample_01_near_left, sample_02_near_center
selection_sha256: 2c4052ef4c72a434f7a57b1e075b02d517250c0130c7014ff60443203b0a318a
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: 51145f94d598642b9801572bccfbd0dd434d50f9
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; all six unique points have sealed PASSED attempts; each Worker receives exactly three leases and completes recovery through generation 4; all 12 original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, provenance, hash, and cleanup gates pass; no initiating TF_UNAVAILABLE, CUP_POSE_TIMEOUT, BROKER_NOT_READY, or controller abort occurs; execution_complete, batch_cleanup_complete, coverage_complete, and qualification_passed are true; execute-mode validation fields remain false and inapplicable; no residual owned state remains.
failure_rule: Any nonzero exit, FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, recovery or cleanup failure, applicable qualification false, or residual owned state makes this batch non-qualifying and requires diagnosis before later gates.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: The command exited 1 in 0.19 seconds with BROKER_IMAGE_MISMATCH because the invocation misspelled the frozen image tag as jazilho instead of jazzy. Admission created no batch root, container, GPU task, ROS process, or physical action. This is invalid command-transcription evidence, not a product result.
retained: command log, time, exit, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke and command evidence, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
```

## EXP-083 — Corrected F74 admissible six-point execute regression

```yaml
experiment_id: EXP-083
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:35:25+08:00
  - status: RUNNING
    at: 2026-09-13T05:36:03+08:00
  - status: VALID
    at: 2026-09-13T05:44:39+08:00
prior_experiment: EXP-082
hypothesis: The corrected invocation of the same F74 runtime will reproduce EXP-081's six PASSED points under the execute-correct acceptance contract.
single_variable: Correct the image tag typo from jazilho to the immutable registered jazzy tag; all product inputs and acceptance criteria remain EXP-082-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-diagnostic-execute-20260913-v6-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-diagnostic-execute-f74-v3
worker_count: 2
max_points_per_worker: 3
selection: task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm, sample_01_near_left, sample_02_near_center
selection_sha256: 2c4052ef4c72a434f7a57b1e075b02d517250c0130c7014ff60443203b0a318a
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: 4b408de27843b0d5890782f6a94a6d99decd2666
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; all six unique points have sealed PASSED attempts; each Worker receives exactly three leases and completes recovery through generation 4; all 12 original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, provenance, hash, and cleanup gates pass; no initiating TF_UNAVAILABLE, CUP_POSE_TIMEOUT, BROKER_NOT_READY, or controller abort occurs; execution_complete, batch_cleanup_complete, coverage_complete, and qualification_passed are true; execute-mode validation fields remain false and inapplicable; no residual owned state remains.
failure_rule: Any nonzero exit, FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, recovery or cleanup failure, applicable qualification false, or residual owned state makes this batch non-qualifying and requires diagnosis before later gates.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: Exit 0 in 278.62 seconds. All six unique points were PASSED; both Workers received exactly K=3 leases and stopped at generation 4; all six recovery receipts succeeded. Aggregate coverage, execution, qualification, and cleanup gates passed. Execute-mode validation fields remained false and inapplicable as required. Fresh original-resolution inspection accepted all 12 RGB images: each initial image showed the upright cup at its distinct catalog position, and every terminal image showed the upright cup inside the red placement target with the gripper open and retreated. No initiating target fault or residual owned state was found.
aggregate_results_sha256: 8f1f0535af834b825485dd815b9c57d9c88a446fc415a7215549dd93ab7fc630
command_log_sha256: 4efc866458ac66c59588923a50023da96493afb14bdc36fedbf32bc3c253ac87
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP083.json
visual_review: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-review-EXP083.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-083-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP083.txt
retained: EXP-083 and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke and command evidence, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
decision: ADVANCE TO NORMAL FOUR-POINT SMALL GATE
```

## EXP-084 — F74 normal four-point small regression gate

```yaml
experiment_id: EXP-084
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:45:38+08:00
  - status: RUNNING
    at: 2026-09-13T05:46:04+08:00
  - status: VALID
    at: 2026-09-13T05:50:46+08:00
prior_experiment: EXP-083
hypothesis: The immutable F74 runtime will preserve the accepted normal two-Worker four-point physical schedule before synchronized fault and full-catalog gates.
single_variable: Replace the six-point diagnostic selection and K=3 with the frozen normal small-gate selection and K=2; source, install, image, models, config, catalog, lifecycle, and execute behavior remain fixed.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f74
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: f542f82a5ee838b0789dc9ebbb33ae40cbfcdc00
  preregistration_base_commit: f5e4c265be7e6cad026f695b12351116814ae020
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; four distinct points PASSED; exactly K=2 leases and generation 3 per Worker; four recovery receipts succeed; all eight original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, provenance, hash, coordinator completion, qualification, and cleanup gates pass; execute-mode validation fields remain false and inapplicable; no residual owned state remains.
failure_rule: Any nonzero exit, FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, recovery or cleanup failure, qualification false, or residual owned state makes this batch non-qualifying and requires diagnosis before fault/full gates.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: Exit 0 in 197.97 seconds. All four distinct points PASSED; each Worker received exactly K=2 leases and completed two successful recoveries before stopping at generation 3. All four sealed attempt manifests passed file size and SHA-256 readback and all dynamic manifests were DONE. Aggregate coordinator completion, qualification, and cleanup passed; execute-mode validation fields remained false and inapplicable. Fresh original-resolution inspection accepted all eight RGB images, with distinct upright initial cup positions and upright target placement plus open-gripper retreat in every terminal image. Exact post-exit audit found no owned process, task container, GPU compute application, or related process.
aggregate_results_sha256: c550f27a3187f0262db1375a1e6f8b322704a2374231198a45626cda83aa8ebf
command_log_sha256: 8be4b01f3d1958a9ffae3684d864f1d6b6625c044225831bee3c48af6a55745b
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP084.json
visual_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP084.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-084-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP084.txt
retained: complete live-small-f74 tree, command/MuJoCo/result/visual/cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke and command evidence, diagnosis runtime copies, and invalid diagnostic batches; no deletion authorized
decision: ADVANCE TO SYNCHRONIZED CONTROLLED PLAN-ONLY FAULT GATE
```

## EXP-085 — F74 synchronized controlled plan-only fault gate

```yaml
experiment_id: EXP-085
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:52:26+08:00
  - status: RUNNING
    at: 2026-09-13T05:53:11+08:00
  - status: INVALID
    at: 2026-09-13T05:55:38+08:00
prior_experiment: EXP-084
hypothesis: Exact worker-01 TERM will remain request-local to healthy Broker g1, and subsequent exact Broker g1 TERM will pause grants and recover to healthy ready g2 without physical action, duplicate lease, or K over-debit.
single_variable: Change only execute mode to the approved synchronized plan-only Worker/Broker TERM sequence; source, install, image, config, catalog, models, N=2, K=2, and four-point selection remain fixed from EXP-084.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v1-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f74
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
fault_sequence:
  - wait for Broker g1 ready and worker-01 validation working, then inject exact manifest-owned worker-01 TERM
  - require Broker remains the same healthy g1 while worker-01 advances generation, then inject exact manifest-owned Broker g1 TERM
  - require journal unhealthy/healthy transition and ready model-loaded broker-g2 before judging
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: 82654b38f660079a4824c7ba88c22f0cd1b3a3a9
  preregistration_base_commit: b7382569714b1dac56df11fdfa0cac94795f23e0
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
success_criteria: Both exact injectors exit 0; all four physical statuses remain UNRUN; the target Worker fault is fenced with physical action proven absent and a new Worker generation admitted; Broker g1 stays healthy across Worker disconnect; explicit g1 TERM produces an unhealthy/healthy journal pair and ready model-loaded g2; no lease is granted during the unhealthy window; each stable Worker slot receives exactly two unique leases despite generation changes; coordinator cleanup and exact residual audit pass.
failure_rule: Wrong or drifting process identity, injector failure, physical action, Broker death caused by Worker disconnect, missing unhealthy/healthy transition, no ready g2, lease grant during pause, duplicate point, K over-debit, incomplete cleanup, or residual owned state makes the gate INVALID and blocks full-20 admission.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: The exact manifest-owned worker-01 TERM injector exited 0 after verified Broker g1/model readiness and a worker-01 validation working directory. The external synchronizer then remained in its replacement-Worker observation step and never executed the preregistered exact Broker TERM. The product completed conservative plan-only processing in 83.82 seconds: all four physical statuses remained UNRUN, both stable slots stayed at K=2, and cleanup passed with an empty owned-process manifest. This is INVALID orchestration evidence because the two-fault sequence was incomplete, not a product regression. The exact stale observer process was then terminated and the residual audit was clean.
aggregate_results_sha256: 89bd2987a86678d2d9e45ba5052dba5e1838631be09ab5b874cd636a71509d5c
command_log_sha256: 715a807fca2d86e696b104e0c09bfb6c9982c1494dc9595a545c917362d59fcf
root_cause_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/root-cause-EXP085.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-085-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP085.txt
retained: complete live-fault-f74 tree, command/Worker-injector/MuJoCo/root-cause/cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke and command evidence, diagnosis runtime copies, invalid diagnostic batches, and this incomplete fault batch; no deletion authorized
decision: RERUN SYNCHRONIZED FAULT GATE WITH PERSISTENT OBSERVER SESSION
```

## EXP-086 — F74 persistent-observer synchronized plan-only fault gate

```yaml
experiment_id: EXP-086
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:56:24+08:00
  - status: RUNNING
    at: 2026-09-13T05:56:49+08:00
  - status: INVALID
    at: 2026-09-13T05:57:20+08:00
prior_experiment: EXP-085
hypothesis: Keeping the external synchronizer in a persistent command session will complete the already-approved exact Worker/Broker TERM sequence and demonstrate F74 fault isolation and recovery.
single_variable: External observer lifetime only; all product inputs, plan-only mode, N=2, K=2, selection, readiness predicates, exact identity-fenced TERM targets, and acceptance criteria remain EXP-085-identical.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v2-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f74-v2
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
fault_sequence:
  - wait for Broker g1 ready and worker-01 validation working, then inject exact manifest-owned worker-01 TERM
  - require the same Broker g1 PID remains healthy while a different worker-01 PID is admitted, then inject exact manifest-owned Broker g1 TERM
  - require a different manifest-owned Broker PID plus ready.json and .model-ready.json under broker-g2
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: eee17b98fef9a843060affe41f31505990b03519
  preregistration_base_commit: 35e5642d073d93505a674bb1104a150ab2740f76
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
success_criteria: Both exact injectors exit 0; all physical statuses remain UNRUN; worker-01 fault is fenced with physical action proven absent and a new Worker generation admitted; Broker g1 remains healthy across Worker disconnect; exact g1 TERM yields a journal unhealthy/healthy pair and ready model-loaded g2; no lease grant occurs during the unhealthy window; each stable slot receives exactly two unique leases; cleanup and residual audit pass.
failure_rule: Any missing or wrong target, identity drift, injector failure, physical action, Worker-induced Broker death, missing ready g2 or health transition, lease during pause, duplicate point, K over-debit, cleanup failure, or residual owned state makes this run INVALID and blocks full-20 admission.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: The command exited 1 in 0.33 seconds with YOLO_HASH_MISMATCH because the invocation duplicated part of the frozen expected hash literal. Admission created no batch root, container, GPU task, ROS process, or physical action. This is invalid command-transcription evidence, not a product result.
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP086.json
retained: command log/time/exit and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke and command evidence, diagnosis runtime copies, invalid diagnostic batches, and incomplete fault batches; no deletion authorized
decision: RERUN IDENTICAL PERSISTENT-OBSERVER FAULT GATE WITH CORRECT FROZEN HASH
```

## EXP-087 — Corrected F74 persistent-observer fault gate

```yaml
experiment_id: EXP-087
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T05:57:40+08:00
  - status: RUNNING
    at: 2026-09-13T05:58:04+08:00
  - status: INVALID
    at: 2026-09-13T06:01:55+08:00
prior_experiment: EXP-086
hypothesis: The correctly transcribed immutable invocation plus persistent observer will complete the approved synchronized Worker/Broker TERM sequence and demonstrate F74 fault isolation and recovery.
single_variable: Correct only the duplicated YOLO expected-hash literal; product inputs and EXP-086 fault procedure/acceptance remain fixed.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v3-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f74-v3
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
fault_sequence:
  - wait for Broker g1 ready and worker-01 validation working, then inject exact manifest-owned worker-01 TERM
  - require the same Broker g1 PID remains healthy while a different worker-01 PID is admitted, then inject exact manifest-owned Broker g1 TERM
  - require a different manifest-owned Broker PID plus ready.json and .model-ready.json under broker-g2
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: dc57256f66b0d9e363cd1520116e4476952da241
  preregistration_base_commit: 6392e20f296b34d2e2f2d40959ef410f8fb7a2b4
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
success_criteria: Both exact injectors exit 0; all physical statuses remain UNRUN; worker-01 fault is fenced with physical action proven absent and a new Worker generation admitted; Broker g1 remains healthy across Worker disconnect; exact g1 TERM yields a journal unhealthy/healthy pair and ready model-loaded g2; no lease grant occurs during the unhealthy window; each stable slot receives exactly two unique leases; cleanup and residual audit pass.
failure_rule: Any missing or wrong target, identity drift, injector failure, physical action, Worker-induced Broker death, missing ready g2 or health transition, lease during pause, duplicate point, K over-debit, cleanup failure, or residual owned state makes this run INVALID and blocks full-20 admission.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: The exact worker-01 TERM injector again exited 0 with physical action absent, and the product completed all four plan-only points as UNRUN with K=2 per slot and complete cleanup in 84.56 seconds. The persistent observer was retained correctly but its simultaneous replacement-PID manifest predicate was not a valid durable recovery predicate; it did not advance to Broker TERM although the coordinator journal later recorded worker-01 generation recovery. The observer was explicitly stopped after batch exit. This is INVALID observer-authoring evidence, not a product failure.
aggregate_results_sha256: 89bd2987a86678d2d9e45ba5052dba5e1838631be09ab5b874cd636a71509d5c
command_log_sha256: 5c9e87a9810e0560f8c7a98d3b44598241b60c408aa488f0a89a1d7aadde47aa
root_cause_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/root-cause-EXP087.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-087-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP087.txt
retained: complete live-fault-f74-v3 tree, command/Worker-injector/MuJoCo/root-cause/cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke/command/diagnostic evidence, and incomplete fault batches; no deletion authorized
decision: RERUN WITH DURABLE COORDINATOR WORKER_RECOVERED EVENT AS THE POST-WORKER SYNCHRONIZATION PREDICATE
```

## EXP-088 — F74 journal-synchronized controlled plan-only fault gate

```yaml
experiment_id: EXP-088
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T06:02:26+08:00
  - status: RUNNING
    at: 2026-09-13T06:03:11+08:00
  - status: VALID
    at: 2026-09-13T06:05:41+08:00
prior_experiment: EXP-087
hypothesis: Synchronizing Broker TERM on the durable worker-01 generation-2 WORKER_RECOVERED journal event will complete the approved exact two-fault sequence and demonstrate F74 fault recovery.
single_variable: Replace only the invalid transient replacement-PID predicate with the journal-authoritative worker-01 generation-2 WORKER_RECOVERED predicate; product inputs, persistent observer, plan-only mode, N/K, selection, exact TERM targets, and acceptance remain fixed.
mode: plan_only; no trajectory execution or physical action
lifecycle: ISOLATED_STACK
batch_id: parallel-fault-plan-20260913-v4-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-fault-f74-v4
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
fault_sequence:
  - wait for Broker g1 ready and worker-01 validation working, then inject exact manifest-owned worker-01 TERM
  - require durable worker-01 generation-2 WORKER_RECOVERED plus the same healthy Broker g1 PID, then inject exact manifest-owned Broker g1 TERM
  - require a different manifest-owned Broker PID plus ready.json and .model-ready.json under broker-g2
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: 2e2ff4b5ea69538f20ca1a9c50af2e891fd6ed8c
  preregistration_base_commit: 89cb9e22c185ad60e60a2e441ae44eb312ea1ab3
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
success_criteria: Both exact injectors exit 0; all physical statuses remain UNRUN; worker-01 fault is fenced with physical action proven absent and durable recovery; Broker g1 remains healthy across Worker disconnect; exact g1 TERM yields a journal unhealthy/healthy pair and ready model-loaded g2; no lease grant occurs during the unhealthy window; each stable slot receives exactly two unique leases; cleanup and residual audit pass.
failure_rule: Any missing or wrong target, identity drift, injector failure, physical action, Worker-induced Broker death, missing ready g2 or health transition, lease during pause, duplicate point, K over-debit, cleanup failure, or residual owned state makes this run INVALID and blocks full-20 admission.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: Both exact manifest-owned TERM injectors exited 0. Worker-01 generation 1 was terminated only after Broker g1/model readiness and a validation working directory; its recovery gates proved fenced, stopped, confirmed, ready, recovered, and physical_action_proven_absent, and the journal durably recorded generation-2 recovery while Broker g1 retained the same PID and readiness. Exact Broker g1 TERM then yielded BROKER_HEALTH_CHANGED false at sequence 90 and true at sequence 109 plus a distinct ready/model-loaded Broker g2. No LEASE_GRANTED event occurred in that unhealthy window; the adjacent grants were sequence 86 before and 111 after. All four unique physical statuses remained UNRUN, each stable Worker slot received exactly K=2 leases and stopped at generation 3, all four plan-only recoveries succeeded, and cleanup/residual gates passed. The main plan-only command's exit 1 and validation_passed=false are expected because injected validations are deliberately invalid; fault-gate validity is determined by the preregistered fault invariants.
aggregate_results_sha256: 89bd2987a86678d2d9e45ba5052dba5e1838631be09ab5b874cd636a71509d5c
command_log_sha256: 1c47404ebfdd25fbcf61bb3dec2b69975a42c67ac91e65c67d2f9db21009dad0
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP088.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-088-cleanup-audit.json
worker_injector_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-worker-088.json
broker_injector_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-broker-088.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP088.txt
retained: complete live-fault-f74-v4 tree, command/injector/synchronization/MuJoCo/result/cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke and command evidence, diagnosis runtime copies, invalid diagnostic batches, and superseded fault batches; no deletion authorized
decision: ADVANCE TO IMMUTABLE FULL 20-POINT QUALIFICATION
```

## EXP-089 — F74 immutable full 20-point qualification

```yaml
experiment_id: EXP-089
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T06:07:08+08:00
  - status: RUNNING
    at: 2026-09-13T06:07:37+08:00
  - status: INVALID
    at: 2026-09-13T06:19:46+08:00
prior_experiment: EXP-088
hypothesis: The immutable F74 runtime will execute and seal all 20 frozen catalog points exactly once with dynamic two-Worker scheduling, K=10 per stable slot, exact-TF localization, YOLO-first perception, complete recovery, and no residual state.
single_variable: Expand EXP-084 from the four-point selection and K=2 to the complete frozen catalog and K=10; source, install, image, models, config, catalog, N=2, lifecycle, and execute behavior remain byte-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-20-20260913-v1-f74
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f74
worker_count: 2
max_points_per_worker: 10
selection: complete frozen 20-point catalog; no --point-id filter
selection_sha256: 33374bb01c31f342e6a2f3d13943c91e74d62165a5a901678216bbb18ffa9a64
preflight:
  related_processes: none
  containers: none
  gpu_compute_applications: none
  host_memory_available: 24 GiB
  gpu_memory_free: 15269 MiB
provenance:
  executable_source_commit: 853c2271048d3dfcf1e801d20d4554f0e7af2201
  preregistration_commit: 0b72ec074aad9dc4262346875f73fc8d7c4c28e9
  preregistration_base_commit: 812f2ee1749e537aec59769a7ec57ba8bd87eafb
  executable_source_tree: 7ff410a3a9a823c49f77a7483417080060bc395b93f74769d76a10c8190d09a3
  installed_module_tree: 68f0f7f6977df926b94c8555c06419f9bf1f613c1423c75d435ed017cc2e145a
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  broker_image_id: sha256:106a34fa7a5d0e69e05d66e122e6f3fa1aab54ce0afca7108eed219e62a61d42
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; all 20 catalog points have unique leases and sealed PASSED attempts; exactly K=10 leases and generation 11 per Worker; all 20 recovery receipts succeed; all 40 original RGB images pass fresh original-resolution inspection; numeric, dynamic, recovery, model, exact-TF, provenance, manifest file-size/SHA-256, coordinator completion, qualification, and cleanup gates pass; execute-mode validation fields remain false and inapplicable; no residual owned state remains.
failure_rule: Any nonzero exit, FAILED, INDETERMINATE, UNRUN, INVALID, duplicate or missing point, K violation, evidence or hash mismatch, visual rejection, recovery or cleanup failure, qualification false, target fault, or residual owned state makes this batch non-qualifying; diagnose before any rerun.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: The immutable command exited 1 after 351.18 seconds. task_start and the three cup-test anchors passed, after which each Worker repeatedly received BrokerResponse.INFRA_ERROR/BROKER_NOT_READY for its first sample point; the remaining 16 catalog points therefore remained UNRUN and qualification_passed=false. Both stable slots consumed exactly K=10 leases and stopped at generation 11. All 20 recovery receipts succeeded, all invalid attempts proved physical action absent, all 20 attempt manifests and 108 listed files passed size/SHA-256 readback, and cleanup/residual gates passed. Fresh original-resolution inspection accepted all eight initial/terminal images from the four passed points. CUP_POSE_TIMEOUT is downstream of the missing pose publication, not the initiating failure.
aggregate_results_sha256: 29046c8bce491dbf2c8877f1f57b6b66fe89646ee4a06c9f24def051c44053a0
command_log_sha256: 96cf19c1ef350a9e731b5348f0375c15045488c77b79e2e0e36b2188ccbee97a
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP089.json
root_cause_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/root-cause-EXP089.json
visual_inspection: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP089.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-089-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP089.txt
retained: complete live-20-f74 tree, command/MuJoCo/result/root-cause/visual/cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build scratch, invalid smoke and command evidence, diagnosis runtime copies, invalid diagnostic batches, superseded fault batches, and this non-qualifying full batch; no deletion authorized
decision: IMPLEMENT FIRST-INFRASTRUCTURE-ERROR DIAGNOSTIC WITH TDD, REBUILD, AND REPEAT FULL QUALIFICATION
```

## EXP-090 — First infrastructure-failure diagnostic

```yaml
experiment_id: EXP-090
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T06:21:45+08:00
  - status: VALID
    at: 2026-09-13T06:31:31+08:00
prior_experiment: EXP-089
hypothesis: A first-writer-wins durable diagnostic at the runtime/service health boundary will preserve the initiating exception or Broker response that EXP-089 currently collapses to BROKER_NOT_READY, without changing any inference outcome, scheduling, or safety decision.
single_variable: Add diagnostic emission and a mode-0600 canonical first-failure receipt; leave all runtime classification, Broker readiness, transport, model, deadline, and physical-action behavior unchanged.
method: Add RED tests for exact runtime exception capture and first-writer preservation, implement the minimum diagnostic path, run focused and package gates with registered ai-station NVMe scratch, rebuild the immutable image, smoke it, and repeat the full catalog with a new batch ID.
success_criteria: RED tests fail for the missing receipt; GREEN tests prove exact reason/type/identity, canonical JSON, mode 0600, and first-writer preservation; ordinary package tests and static gates pass; image provenance and smoke pass; a fresh full run either qualifies 20/20 or durably exposes the initiating infrastructure error.
failure_rule: Any changed inference decision, overwritten first failure, missing/unsafe receipt, test or gate failure, provenance drift, cleanup failure, or unexplained full-run failure makes this experiment INVALID.
retention_rule: Retain all evidence and registered scratch as deletion candidates; delete nothing without explicit user authorization.
result: The valid RED failed only because the first-failure receipt was absent. The focused module gate then passed 81 tests, including exact runtime exception capture, canonical mode-0600 receipt readback, first-writer preservation, and Broker queue-timeout capture. The phase-separated short-root ordinary package gate built successfully and passed 2801 tests with zero errors, failures, or skips in 84.31 seconds; benchmark_test was not collected. Git/submodule cleanliness, compileall, installed path, catalog/config/model hashes, and source provenance passed. The rebuilt immutable image sha256:7d1067110ff8f8a244dbf976c0297d73ba53fdeebbd5e444d03bf00ffbc757d2 carries source hash 58a02ab45ec0df072e7a7e23f28dfaeec3e25034a7fb9e792dc75fc1d0f6fd68, and both YOLO and Grounded-SAM returned one QUALIFIED candidate in the offline CUDA smoke with clean container/GPU teardown.
implementation_commit: a2397d97d6c367be9b4dd60b049d8ee9ec91df5c
static_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/f90-static-gates.json
package_gate_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p113
package_test_result: 2801 tests, 0 errors, 0 failures, 0 skipped
image_id: sha256:7d1067110ff8f8a244dbf976c0297d73ba53fdeebbd5e444d03bf00ffbc757d2
source_tree_sha256: 58a02ab45ec0df072e7a7e23f28dfaeec3e25034a7fb9e792dc75fc1d0f6fd68
smoke_batch: task14-f90-smoke; YOLO QUALIFIED in 34.761185 ms; Grounded-SAM QUALIFIED in 193.084648 ms
retained: all RED/GREEN/package/static/image/smoke evidence, invalid harness evidence, and prior evidence
archived: none
deletion_candidates: every registered EXP-090 pytest/build/compile scratch plus prior candidates; no deletion authorized
decision: RUN A NEW FOUR-POINT TWO-WORKER EXECUTE GATE BEFORE REPEATING THE FULL CATALOG
```

## EXP-091 — F90 normal four-point small regression gate

```yaml
experiment_id: EXP-091
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T06:32:37+08:00
  - status: RUNNING
    at: 2026-09-13T06:33:19+08:00
  - status: VALID
    at: 2026-09-13T06:38:18+08:00
prior_experiment: EXP-090
hypothesis: The diagnostic-only F90 image preserves the accepted two-Worker four-point physical behavior while making any first health-losing perception failure durable.
single_variable: Add F90 first-failure diagnostics to the F74 source and Broker image; selection, N=2, K=2, config, catalog, models, MuJoCo/MoveIt runtime, deadlines, safety decisions, and execute behavior remain fixed from EXP-084.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f90
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f90
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
preflight: No related process, task container, or GPU compute application; 24 CPUs, 24.771 GiB MemAvailable, 15272 MiB GPU free; batch root absent.
provenance:
  executable_source_commit: a2397d97d6c367be9b4dd60b049d8ee9ec91df5c
  preregistration_commit: e163b2fb8f22fba0fd14b42fb625de1e593521bb
  preregistration_base_commit: a2397d97d6c367be9b4dd60b049d8ee9ec91df5c
  executable_source_tree: 58a02ab45ec0df072e7a7e23f28dfaeec3e25034a7fb9e792dc75fc1d0f6fd68
  installed_module_tree: de4b36f48b4b4446c0efa315dd52dd941334088f770897a1636e039e499231ff
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  broker_image_id: sha256:7d1067110ff8f8a244dbf976c0297d73ba53fdeebbd5e444d03bf00ffbc757d2
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; all four distinct points PASSED; exactly K=2 leases and generation 3 per Worker; four successful recoveries; all eight original RGB images accepted; numeric, dynamic, exact-TF, model, provenance, manifest hash, coordinator completion, qualification, and cleanup gates pass; no first-failure receipt and no residual owned state.
failure_rule: Any nonzero exit, non-PASSED point, unexpected first-failure receipt, K/generation violation, evidence/hash/visual/recovery/cleanup failure, qualification false, or residual state blocks a new full-catalog run.
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
result: The F90 command exited 0 in 206.87 seconds. All four distinct points PASSED, each Worker received exactly K=2 leases and reached generation 3 through two successful recoveries, all four dynamic manifests were DONE, and no first-failure receipt was produced. All four sealed attempt manifests and their 44 listed files passed size/SHA-256 readback. Aggregate qualification and cleanup passed, execute-mode validation fields remained false and inapplicable, and fresh original-resolution inspection accepted all eight initial/terminal frames. Post-exit audit found no owned process, task container, GPU compute application, or related process.
aggregate_results_sha256: c550f27a3187f0262db1375a1e6f8b322704a2374231198a45626cda83aa8ebf
command_log_sha256: 30e0be83d84dced10b681128bb06d1c95a34cdbcb626e2bdfa7d0fa26b8e0d05
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP091.json
visual_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP091.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-091-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP091.txt
retained: complete live-small-f90 tree, command/MuJoCo/result/visual/cleanup reports, F90 qualification evidence, and all prior evidence
archived: none
deletion_candidates: registered pytest/build/compile scratch and all prior candidates; no deletion authorized
decision: ADVANCE TO A NEW IMMUTABLE FULL 20-POINT F90 QUALIFICATION
```

## EXP-092 — F90 immutable full 20-point qualification

```yaml
experiment_id: EXP-092
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T06:40:27+08:00
  - status: RUNNING
    at: 2026-09-13T06:41:03+08:00
  - status: INVALID
    at: 2026-09-13T06:48:39+08:00
prior_experiment: EXP-091
hypothesis: The fully qualified F90 runtime will complete the frozen 20-point catalog and either qualify 20/20 or preserve the exact initiating perception infrastructure failure that F74 concealed.
single_variable: Expand EXP-091 from its four-point selection and K=2 to the complete frozen catalog and K=10; source, install, image, models, config, catalog, N=2, lifecycle, execute behavior, and diagnostics remain byte-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-20-20260913-v1-f90
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f90
worker_count: 2
max_points_per_worker: 10
selection: complete frozen 20-point catalog; no --point-id filter
selection_sha256: 33374bb01c31f342e6a2f3d13943c91e74d62165a5a901678216bbb18ffa9a64
preflight: No related process, task container, or GPU compute application; 24 CPUs, 25.052 GiB MemAvailable, 15272 MiB GPU free; batch root absent; exact F90 image and worktree console reverified.
provenance:
  executable_source_commit: a2397d97d6c367be9b4dd60b049d8ee9ec91df5c
  preregistration_commit: 20414c027b0f6d0c881435041bf4c9a49bedf2f6
  preregistration_base_commit: f93570568f5138eac14bc7d3cc6d6563dc01cd7f
  executable_source_tree: 58a02ab45ec0df072e7a7e23f28dfaeec3e25034a7fb9e792dc75fc1d0f6fd68
  installed_module_tree: de4b36f48b4b4446c0efa315dd52dd941334088f770897a1636e039e499231ff
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  broker_image_id: sha256:7d1067110ff8f8a244dbf976c0297d73ba53fdeebbd5e444d03bf00ffbc757d2
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; all 20 catalog points have unique leases and sealed PASSED attempts; exactly K=10 leases and generation 11 per Worker; all 20 recoveries succeed; all 40 original RGB images pass fresh inspection; YOLO-first/fallback usage is attributable; numeric, dynamic, exact-TF, model, provenance, manifest size/SHA-256, coordinator completion, qualification, and cleanup gates pass; no failure receipt or residual owned state.
failure_rule: Any nonzero exit, non-PASSED point, duplicate/missing point, K/generation violation, evidence/hash/visual/recovery/cleanup failure, qualification false, or residual state makes this batch non-qualifying. If perception health is lost, the first-failure receipt and command log must be read before deciding the next fix.
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
result: The command exited 1 after 345.31 seconds with 4 PASSED anchors and 16 UNRUN catalog points after 16 fail-closed PERCEPTION_INFRA_ERROR attempts. F90 durably preserved the initiator: the already delivered and physically PASSED cup_test_right_5cm YOLO request was later reclassified as BrokerResponse.INFERENCE_TIMEOUT/INFERENCE_DEADLINE_EXCEEDED. The identical request ID appears in that point's POSE_ACCEPTED evidence, proving inference completed and was consumed before the later timeout. PerceptionService kept the completed request in its historical _requests scan, while PerceptionBroker._guard reapplied the deadline to terminal QUALIFIED responses; that historical timeout poisoned Broker health and produced downstream BROKER_NOT_READY. Both Workers consumed K=10 and stopped at generation 11, all 20 recoveries succeeded, all invalid attempts proved no physical action, all 20 manifests and 108 listed files passed size/SHA-256 readback, all eight anchor originals were visually accepted, and cleanup/residual gates passed.
aggregate_results_sha256: 29046c8bce491dbf2c8877f1f57b6b66fe89646ee4a06c9f24def051c44053a0
first_failure_receipt_sha256: 6179646523533f0506bda4c2b04cda063a3067e402d2d340c0831c134ef8287a
command_log_sha256: bff3e7f9a1d8baff6971d091d5701cd2797c93eec6dcbb9032504f7c4d508a89
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP092.json
root_cause_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/root-cause-EXP092.json
visual_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP092.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-092-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP092.txt
retained: complete live-20-f90 tree including the first-failure receipt, command/MuJoCo/result/root-cause/visual/cleanup reports, and all prior evidence
archived: none
deletion_candidates: registered pytest/build/compile scratch, non-qualifying full batches, invalid harness attempts, and all prior candidates; no deletion authorized
decision: TDD-RETIRE DELIVERED TERMINAL RESPONSES FROM SERVICE DEADLINE SYNCHRONIZATION, THEN REQUALIFY STATIC/IMAGE/SMALL/FULL
```

## EXP-093 — Retire delivered service responses from deadline synchronization

```yaml
experiment_id: EXP-093
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T06:49:34+08:00
  - status: VALID
    at: 2026-09-13T06:58:12+08:00
prior_experiment: EXP-092
hypothesis: Removing a request from PerceptionService's deadline-synchronization set immediately after its terminal response is delivered will prevent a later poll from converting a consumed QUALIFIED result into INFERENCE_TIMEOUT, while preserving all Broker pre-delivery guards and new-request timeouts.
single_variable: Retire only delivered terminal responses from PerceptionService._requests; do not change PerceptionBroker guards, deadlines, inference classification, model behavior, or physical safety gates.
method: Add a fake-clock RED test that delivers a timely QUALIFIED response, advances beyond its inference deadline, and submits a second request; require the old response to remain out of _sync_health and the service to remain healthy. Then run focused/adjacent/package gates, rebuild/smoke the image, and repeat small/full execute batches.
success_criteria: RED reproduces the historical timeout; GREEN preserves health and accepts the second request while existing timeout and initiating-failure tests pass; all static/package/image/smoke/small/full gates subsequently pass.
failure_rule: Any loss of pre-delivery fencing/deadline behavior, altered model outcome, test/gate failure, evidence or cleanup failure, or non-qualifying runtime batch makes the applicable experiment invalid and requires diagnosis.
retention_rule: Retain all evidence and scratch; delete nothing without explicit user authorization.
result: The valid fake-clock RED reproduced the EXP-092 failure exactly: after a timely QUALIFIED response was delivered, advancing past its old deadline caused the second request to be rejected BROKER_NOT_READY. The minimum service-side change retires a request from PerceptionService._requests only after its terminal response is delivered; Broker guards and all pre-delivery deadline behavior are unchanged. The focused GREEN passed 3 tests, adjacent runtime/Broker gate passed 160, the complete parallel suite passed 1085, and the phase-separated ordinary package gate passed 2802 with zero errors, failures, or skips in 83.97 seconds. Static provenance passed with source hash 052dae12a2a46dab28d8e4e9c55dc0930df856c0890b2c9197eaa8bce2a04970 and installed module hash 4aae546b05dfd3aaace20566df98fd9dd53e671d0c2b0c71bb4cea3fb0147f6b. The rebuilt image sha256:d4c8efc976804ae289df50259104147b8030e823927a2070262f471c2b44ff97 preserved that source hash, and both YOLO and Grounded-SAM returned QUALIFIED in the offline CUDA smoke with clean container/GPU teardown.
implementation_commit: ed91c14cc3476fae07847e6907b6d11684ba9d46
static_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/f91-static-gates.json
package_gate_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p115
package_test_result: 2802 tests, 0 errors, 0 failures, 0 skipped
image_id: sha256:d4c8efc976804ae289df50259104147b8030e823927a2070262f471c2b44ff97
source_tree_sha256: 052dae12a2a46dab28d8e4e9c55dc0930df856c0890b2c9197eaa8bce2a04970
installed_module_tree_sha256: 4aae546b05dfd3aaace20566df98fd9dd53e671d0c2b0c71bb4cea3fb0147f6b
smoke_batch: task14-f91-smoke; YOLO QUALIFIED in 34.095614 ms; Grounded-SAM QUALIFIED in 193.843765 ms
retained: all RED/GREEN/adjacent/parallel/package/static/image/smoke evidence and all prior evidence
archived: none
deletion_candidates: every registered EXP-093 pytest/build/compile scratch plus all prior candidates; no deletion authorized
decision: RUN A NEW FOUR-POINT TWO-WORKER EXECUTE GATE BEFORE REPEATING THE FULL CATALOG
```

## EXP-094 — F91 normal four-point small regression gate

```yaml
experiment_id: EXP-094
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T06:59:22+08:00
  - status: RUNNING
    at: 2026-09-13T07:00:15+08:00
  - status: VALID
    at: 2026-09-13T07:06:31+08:00
prior_experiment: EXP-093
hypothesis: The F91 delivered-response retirement preserves the accepted two-Worker four-point physical behavior and prevents completed requests from poisoning later service health.
single_variable: Replace F90 with F91, whose only runtime change retires delivered terminal service responses; selection, N=2, K=2, config, catalog, models, MuJoCo/MoveIt runtime, deadlines, safety decisions, and execute behavior remain fixed from EXP-091.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260913-v1-f91
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f91
worker_count: 2
max_points_per_worker: 2
selection: task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right
selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
preflight: No related process, task container, or GPU compute application; 24 CPUs, 25.272 GiB MemAvailable, 15272 MiB GPU free; batch root absent.
provenance:
  executable_source_commit: ed91c14cc3476fae07847e6907b6d11684ba9d46
  preregistration_commit: 1b3fbb77df67adfb0f8142c5833284a93788ff53
  preregistration_base_commit: 3fde94a7f
  executable_source_tree: 052dae12a2a46dab28d8e4e9c55dc0930df856c0890b2c9197eaa8bce2a04970
  installed_module_tree: 4aae546b05dfd3aaace20566df98fd9dd53e671d0c2b0c71bb4cea3fb0147f6b
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  broker_image_id: sha256:d4c8efc976804ae289df50259104147b8030e823927a2070262f471c2b44ff97
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; all four distinct points PASSED; exactly K=2 leases and generation 3 per Worker; four successful recoveries; all eight original RGB images accepted; numeric, dynamic, exact-TF, model, provenance, manifest hash, coordinator completion, qualification, and cleanup gates pass; no first-failure receipt and no residual owned state.
failure_rule: Any nonzero exit, non-PASSED point, unexpected first-failure receipt, K/generation violation, evidence/hash/visual/recovery/cleanup failure, qualification false, or residual state blocks a new full-catalog run.
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
result: The F91 command exited 0 in 210.45 seconds. All four distinct points PASSED, each Worker received exactly K=2 leases and reached generation 3 through two successful recoveries, all four dynamic manifests were DONE, and no first-failure receipt was produced. All four sealed attempt manifests and their 44 listed files passed size/SHA-256 readback. Aggregate qualification and cleanup passed, execute-mode validation fields remained false and inapplicable, and fresh original-resolution inspection accepted all eight initial/terminal frames. Post-exit audit found no owned process, task container, GPU compute application, or related process. The batch-created worktree MUJOCO_LOG.TXT was moved to the report path; the separate preexisting home-directory log retained its preflight identity and was not misattributed.
aggregate_results_sha256: c550f27a3187f0262db1375a1e6f8b322704a2374231198a45626cda83aa8ebf
command_log_sha256: ffdc4513cdd1fe081b17b98a318b2bb499db65591e2eac97c69d7a37669cf0bd
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP094.json
visual_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP094.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-094-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP094.txt; sha256 00ba18b19b00357511a350f5e485f3f87658d858e1afbf416b2e5f21228572f4
retained: complete live-small-f91 tree, command/result/visual/cleanup reports, F91 static qualification evidence, and all prior evidence
archived: none
deletion_candidates: registered pytest/build/compile scratch and all prior candidates; no deletion authorized
decision: ADVANCE TO A NEW IMMUTABLE FULL 20-POINT F91 QUALIFICATION
```

## EXP-095 — F91 immutable full 20-point qualification

```yaml
experiment_id: EXP-095
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T07:07:30+08:00
  - status: RUNNING
    at: 2026-09-13T07:08:18+08:00
  - status: VALID
    at: 2026-09-13T07:24:37+08:00
prior_experiment: EXP-094
hypothesis: The statically and four-point-qualified F91 runtime will complete and qualify the complete frozen 20-point catalog without historical delivered responses poisoning perception health.
single_variable: Expand EXP-094 from its four-point selection and K=2 to the complete frozen catalog and K=10; source, install, image, models, config, catalog, N=2, lifecycle, execute behavior, and service-response retirement remain byte-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-20-20260913-v1-f91
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f91
worker_count: 2
max_points_per_worker: 10
selection: complete frozen 20-point catalog; no --point-id filter
selection_sha256: 33374bb01c31f342e6a2f3d13943c91e74d62165a5a901678216bbb18ffa9a64
preflight: No related process, task container, or GPU compute application; 24 CPUs, 25.759 GiB MemAvailable, 15269 MiB GPU free; batch root absent; exact F91 image and clean worktree reverified.
provenance:
  executable_source_commit: ed91c14cc3476fae07847e6907b6d11684ba9d46
  preregistration_commit: 9e5136c6b486996f6328f1897dbcaa6c1f184a1a
  preregistration_base_commit: 5cd4eb53dbc72a42ee58854fb2fd4ec3de1526c7
  executable_source_tree: 052dae12a2a46dab28d8e4e9c55dc0930df856c0890b2c9197eaa8bce2a04970
  installed_module_tree: 4aae546b05dfd3aaace20566df98fd9dd53e671d0c2b0c71bb4cea3fb0147f6b
  mujoco_ros2_control_submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  installed_ros2_control_node_sha256: 96bdf673ae8dfc05e76191cb5f5ad0184f60e637631a1c06a178f525846a2358
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  broker_image_id: sha256:d4c8efc976804ae289df50259104147b8030e823927a2070262f471c2b44ff97
  runtime_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
success_criteria: Exit 0; all 20 catalog points have unique leases and sealed PASSED attempts; exactly K=10 leases and generation 11 per Worker; all 20 recoveries succeed; all 40 original RGB images pass fresh inspection; YOLO-first/fallback usage is attributable; numeric, dynamic, exact-TF, model, provenance, manifest size/SHA-256, coordinator completion, qualification, and cleanup gates pass; no failure receipt or residual owned state.
failure_rule: Any nonzero exit, non-PASSED point, duplicate/missing point, K/generation violation, evidence/hash/visual/recovery/cleanup failure, qualification false, or residual state makes this batch non-qualifying. If a gate fails, read the initiating evidence and diagnose before deciding the next action.
retention_rule: Retain all evidence; archive only superseded auditable batches; delete nothing without explicit user authorization.
result: The immutable F91 command exited 0 in 856.34 seconds and all 20 frozen catalog points PASSED. Each Worker consumed exactly K=10 unique leases, completed ten successful recoveries, and stopped at generation 11. All 20 dynamic execute manifests were DONE; all 20 sealed attempt manifests and all 220 listed files passed independent size/SHA-256 readback. Every accepted pose used the primary plastic-cup-yolo11n-seg-v1 model (20 requests), so Grounded-SAM fallback usage was zero. No first-failure receipt was produced. Aggregate qualification and cleanup passed, execute-mode validation fields remained false and inapplicable, and fresh original-resolution inspection accepted all 40 initial/terminal RGB images. Post-exit audit found no owned process, task container, GPU compute application, or related process. The batch-created MuJoCo log was moved to the report path, while the unrelated home-directory log retained its preflight identity.
aggregate_results_sha256: 454e251dff9a16fa4a7b371fe2fea521359ba76c7d89203bf845c791ec4cf8ea
batch_manifest_sha256: 15b4b3fad1b3d95325bd8708f088f5b9eb106d055dcba7d128aa11dc8282cec0
command_log_sha256: 9feab8fe79d40c29efb282f04e086f1fd5c90b740cc8e0d2c3678b260255d4e5
result_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/result-EXP095.json
visual_report: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP095.json
cleanup_audit: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-095-cleanup-audit.json
mujoco_log: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP095.txt; sha256 f731314264012ea83b3ede5a3065b52f634211e53bb42e32d16844806356556c
retained: complete live-20-f91 and live-small-f91 trees, all final command/MuJoCo/result/visual/cleanup/static/image/smoke evidence, all diagnostic and fault evidence, and all prior evidence
archived: none
deletion_candidates: registered pytest/build/compile scratch, invalid harness evidence, superseded diagnostic/fault/non-qualifying runtime batches, and all prior candidates; no deletion authorized
decision: FULL F91 TWO-WORKER 20-POINT QUALIFICATION PASSED; PREPARE FINAL DURABLE REPORT AND FINAL CLEAN-STATE READBACK
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

## Astra remediation intake — dispatch 290034f0-7026-48b3-ad00-15d84cd37f87

The eight review findings are accepted as hypotheses pending direct code and deterministic evidence,
not as pre-decided defects. Historical `EXP-088`, `EXP-094`, and `EXP-095` remain immutable. The
remediation sequence will use new monotonic experiment and checkpoint IDs, preserve the Broker and
controller safety gates, and require RED before each confirmed behavioral fix. Finding 6 is not a
design-authority conflict: design section 12 explicitly requires Coordinator restart and replay, so
the production CLI path must be verified against that frozen requirement. Finding 7 is also an
advertised conditional capability: the frozen design and config permit at most three Workers only
with independently verified current two-Worker headroom evidence, so the CLI path must either carry
that authority securely or fail with an explicit unsupported contract.

```yaml
checkpoint_id: CP-082
last_valid_experiment: EXP-095
current_hypothesis: Astra finding 1 may allow heartbeat or lease revocation to wait behind a blocked expert execution, delaying controller cancellation and allowing later dynamic goals.
working_tree_status: clean reviewed head e7c8097c79fd04ea8fdb9f59bd280c862eb4ecd5 before this ledger and ignored SDD recovery-index update
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; no ROS, MuJoCo, MoveIt, parallel batch, task container, or GPU compute process was active at intake
confirmed_conclusions:
  - The dispatch receipt contains exactly 290034f0-7026-48b3-ad00-15d84cd37f87 in 36 bytes with no newline.
  - The target worktree is the isolated clean branch codex/so101-parallel-multipoint-validation at e7c8097c79fd04ea8fdb9f59bd280c862eb4ecd5.
  - The current clean submodule checkout and gitlink are c16b5a5fe880b6e1857f56486dab4ae726576969.
  - The installed so101_demo_py prefix resolves inside the target worktree overlay.
  - Historical EXP-095 is the last valid immutable qualification and remains unchanged.
disproven_routes:
  - Treating the stale header current_commit, CP-039, F53 next action, or original 71bc9346 gitlink as the current recovery state.
open_risks:
  - All eight Astra review findings still require direct current-code verification and explicit disposition.
  - Any confirmed runtime safety or recovery defect invalidates reuse of EXP-095 as post-remediation qualification.
next_command: Run EXP-096 deterministic heartbeat/lease revocation RED against the reviewed current Worker and production runtime adapter before modifying production code.
```

## EXP-096 — In-flight heartbeat and lease revocation verification

```yaml
experiment_id: EXP-096
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T09:13:52+08:00
  - status: RUNNING
    at: 2026-09-13T09:19:00+08:00
  - status: VALID
    at: 2026-09-13T09:21:33+08:00
prior_experiment: EXP-095
hypothesis: The current watchdog only records its fault while execute_expert holds the normal runtime path, so controller cancellation and confirmation cannot occur until that blocking call returns, and the dynamic consumer lacks the revoked batch lease needed to fence later goals.
prediction: A deterministic test with execute_expert held in-flight will observe watchdog_faulted=true before release but no cancel-and-confirm call until the block is released; a production-adapter contract test will show no revocation identity reaches the dynamic consumer.
single_variable: Add only deterministic regression tests around the current Worker/runtime revocation boundary; do not change production code in the RED phase.
lifecycle: ISOLATED_STACK
preconditions:
  - reviewed source commit e7c8097c79fd04ea8fdb9f59bd280c862eb4ecd5 and clean c16b5a5fe880b6e1857f56486dab4ae726576969 submodule
  - no live ROS, MuJoCo, MoveIt, Broker, Worker, or task container
  - exact test Python and fresh NVMe scratch verified before pytest
success_criteria:
  - pytest collects the new behavioral tests and fails only at the predicted missing immediate cancellation and revocation propagation boundaries
  - cancellation timing is asserted while execute_expert remains blocked, not after it is released
failure_criteria:
  - the current code already cancels and confirms while blocked and prevents every later goal, disproving the finding
invalid_criteria:
  - import or collection failure, wrong overlay, reused scratch, live-stack interference, or failure unrelated to the asserted boundary
provenance:
  source_commit: e7c8097c79fd04ea8fdb9f59bd280c862eb4ecd5
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_id: not_applicable
  gz_partition: not_applicable
commands:
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-red-ogdqhXfw/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_worker.py::test_watchdog_loss_cancels_and_confirms_while_expert_is_still_blocked src/so101_demo_py/test/test_parallel_worker_runtime.py::test_cancel_motion_retires_exact_dynamic_consumer_before_controller_cancel -q
    exit_code: 1
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-green-U51xBLsR/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_worker.py::test_watchdog_loss_cancels_and_confirms_while_expert_is_still_blocked src/so101_demo_py/test/test_parallel_worker_runtime.py::test_cancel_motion_retires_exact_dynamic_consumer_before_controller_cancel -q
    exit_code: 0
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent-H2emCltc/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_worker.py src/so101_demo_py/test/test_parallel_worker_runtime.py -q
    exit_code: 0
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent2-7HmE8ZfJ/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_worker.py src/so101_demo_py/test/test_parallel_worker_runtime.py -q
    exit_code: 0
observed:
  - RED collected two tests and both failed at the predicted boundaries in 3.48 s wall: the blocked expert saw no cancel/confirm before release, and runtime cancellation left its exact dynamic consumer alive.
  - Focused GREEN collected the same two tests and passed both in 1.14 s pytest / 1.41 s wall.
  - The first adjacent gate passed 152 tests in 3.08 s pytest / 3.35 s wall.
  - After adding direct exact-child/sibling preservation coverage, the final adjacent gate passed 153 tests in 3.14 s pytest / 3.41 s wall.
  - Two intervening command-harness attempts were INVALID before collection because the overlay environment was omitted; they each stopped at ModuleNotFoundError in 0.33-0.34 s wall and are not counted as behavioral evidence.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; watchdog or explicit stop now establishes a global execution fence and starts one idempotent cancel-generation, exact dynamic-consumer stop, controller cancel, and no-active-goal confirmation path without waiting for execute_expert to return. The normal exception path joins the same bounded revocation record rather than duplicating side effects.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-red-ogdqhXfw
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-green-U51xBLsR
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent-H2emCltc
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent2-7HmE8ZfJ
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f1-red-ogdqhXfw.log sha256=be6103629a56cef95e95c96939fafb1950a9b78697a6e28bac1c21456d327cdf
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f1-green-U51xBLsR.log sha256=208e499dc20a394b0939005f44d2c4bd411991470ed5e8126a410c059a73e91e
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f1-adjacent-H2emCltc.log sha256=4e877f46cf32aca195b66222370ce5f8c748fe5b29482de8758cbd4791dc3bdc
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f1-adjacent2-7HmE8ZfJ.stdout sha256=25eaaaac33c6947427309527f889e31f5fa582b9ba8e38c951e318d4e4a509f3
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-red-ogdqhXfw
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-green-U51xBLsR
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent-H2emCltc
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent2-lWuy8a5C
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent2-lqmSnaTC
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f1-adjacent2-7HmE8ZfJ
decision: KEEP
next_experiment: EXP-097
```

```yaml
checkpoint_id: CP-083
last_valid_experiment: EXP-096
current_hypothesis: Astra finding 2 may leave the Coordinator willing to lease new work while the Broker process is alive but reports unhealthy.
working_tree_status: F1 implementation, regression tests, and ledger disposition are ready for one scoped commit; the ignored SDD index is separately updated.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; no ROS, MuJoCo, MoveIt, Broker, Worker, task container, or GPU compute process was started by EXP-096.
confirmed_conclusions:
  - Finding 1 is confirmed and the candidate closes both cancellation timing and exact dynamic-consumer retirement boundaries.
  - Final adjacent evidence is 153 passed in 3.14 s pytest / 3.41 s wall with the exact Python temporary directory inside fresh NVMe scratch.
disproven_routes:
  - Waiting for a blocked execute_expert call to return before canceling the controller or retiring the dynamic consumer.
open_risks:
  - F1 still requires the final ordinary package gate, rebuilt-overlay provenance, and live fault-injection qualification after all reviewed fixes land.
  - Findings 2 through 8 remain pending.
next_command: Commit the scoped F1 source, tests, and ledger, then start EXP-097 with a deterministic alive-but-unhealthy Broker RED test before modifying production code.
```

## EXP-097 — Alive-but-unhealthy Broker propagation verification

```yaml
experiment_id: EXP-097
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T09:24:00+08:00
  - status: RUNNING
    at: 2026-09-13T09:28:00+08:00
  - status: VALID
    at: 2026-09-13T09:32:13+08:00
prior_experiment: EXP-096
hypothesis: A live-serving Broker that returns INFRA_ERROR, QUEUE_TIMEOUT, or INFERENCE_TIMEOUT poisons its local runtime but emits no authenticated generation-bound health-down event, so the Coordinator can remain healthy and issue another lease without triggering exact Broker replacement.
prediction: Deterministic transport/composition tests will observe a health-losing Broker result while coordinator.broker_healthy remains true; a live unhealthy process will not enter the existing exit-only recovery path, and a subsequent lease grant will debit Worker capacity.
single_variable: Add only deterministic regression tests for Broker health-down publication, parent authentication/generation fencing, live-process recovery, and no-debit lease pause; do not change production code in the RED phase.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit e4b5dd293fe3af21ce1dde9fc38abc73c05d6797 with only this ledger PLANNED record uncommitted
  - no live ROS, MuJoCo, MoveIt, Broker, Worker, or task container
  - exact test Python and fresh NVMe scratch must be verified before pytest
success_criteria:
  - RED fails only because no authenticated health-down operation reaches the parent and no alive-unhealthy recovery trigger exists
  - tests freeze accepted health-losing outcomes, stale generation rejection, malformed/forged event rejection, pause-before-recovery, exact generation replacement, and zero lease-count debit while unhealthy
failure_criteria:
  - current code already propagates and authenticates all three health-losing outcomes, pauses lease issuance, and replaces a still-live exact Broker generation
invalid_criteria:
  - import/collection failure, wrong overlay, reused scratch, or a failure outside the intended health propagation/recovery contract
provenance:
  source_commit: e4b5dd293fe3af21ce1dde9fc38abc73c05d6797
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  ros_domain_id: not_applicable
  gz_partition: not_applicable
commands:
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2r-5SHsFv78/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_perception_runtime.py::test_health_losing_response_reports_one_exact_event src/so101_demo_py/test/test_parallel_processes.py::test_wait_replaces_an_exact_broker_that_is_alive_but_reports_unhealthy src/so101_demo_py/test/test_parallel_batch_cli.py::test_authenticated_live_broker_health_down_pauses_without_lease_debit -q
    exit_code: 1
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2g-QmErOwBb/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_perception_runtime.py::test_health_losing_response_reports_one_exact_event src/so101_demo_py/test/test_parallel_processes.py::test_wait_replaces_an_exact_broker_that_is_alive_but_reports_unhealthy src/so101_demo_py/test/test_parallel_batch_cli.py::test_authenticated_live_broker_health_down_pauses_without_lease_debit -q
    exit_code: 0
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2g-ipc-Wz2S2cBo/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_ipc.py::test_broker_transport_authenticates_with_coordinator_before_real_socket_mutation -q
    exit_code: 0
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2a-8gCkkOSb/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_perception_runtime.py src/so101_demo_py/test/test_parallel_ipc.py src/so101_demo_py/test/test_parallel_processes.py src/so101_demo_py/test/test_parallel_batch_cli.py -q
    exit_code: 0
observed:
  - Corrected RED collected five tests and all five failed at the intended missing APIs: no PerceptionService health-down callback, no live-process health probe, and no accepted Broker health-down authority operation. Wall time was 0.84 s.
  - Focused GREEN passed all five behavioral cases in 0.19 s pytest / 0.47 s wall.
  - The direct Broker transport authentication/mutation contract passed in 0.12 s pytest / 0.38 s wall.
  - Final adjacent coverage passed all 194 perception runtime, authenticated IPC, process supervision, and production composition tests in 30.90 s pytest / 31.17 s wall.
  - The first RED harness was INVALID because its long test batch path exceeded the UNIX socket limit after four expected failures; a short fresh scratch produced the authoritative RED. The first GREEN harness was also INVALID because its fake live process never changed poll state after signal; the corrected production-equivalent fake produced the authoritative GREEN. Both invalid scratch trees are retained and classified below.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; each live Broker generation now publishes one authenticated health-down event for INFRA_ERROR, QUEUE_TIMEOUT, or INFERENCE_TIMEOUT. The parent validates exact payload and current generation before setting broker_healthy=false, which pauses new grants without K debit. The supervisor polls that authoritative state even while the exact Broker process is alive, retires only that owned identity, rotates generation authority, and requires the existing ready/model-loaded readmission before marking healthy.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f2r-5SHsFv78.stdout sha256=48f47c1aa2cf484691f349e402fee20c95e8ad1535cb97a349bf0249c76d6057
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f2g-QmErOwBb.stdout sha256=625cd9db075f0d063982baf4c6b8144844ffe79aa412f50047a80fc4dcddb921
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f2g-ipc-Wz2S2cBo.stdout sha256=3be6ffcaecf85b5bd3eef3693ab214b0e7c9eb4e36d117fcf1825652de5eb298
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f2a-8gCkkOSb.stdout sha256=00d0adccd8a3c16e3015d3bb5cd3788e57871b150315905c655702285f4d31bf
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/pytest-remediate-f2-red-WNrcYagX
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2r-5SHsFv78
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2g-k3ncOdJE
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2g-QmErOwBb
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2g-ipc-Wz2S2cBo
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2a-b16RLmlG
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f2a-8gCkkOSb
decision: KEEP
next_experiment: EXP-098
```

```yaml
checkpoint_id: CP-084
last_valid_experiment: EXP-097
current_hypothesis: Astra finding 3 may cause a Worker to exit after successful recovery from an initial-gate failure instead of continuing to lease eligible remaining points.
working_tree_status: F2 implementation, tests, and ledger disposition are ready for one scoped commit; ignored SDD progress remains separately synchronized.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; no ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU compute process was started by EXP-097.
confirmed_conclusions:
  - Finding 2 is confirmed and fixed at the authenticated Broker authority plus exact process-supervision boundary.
  - Stale generation, forged token, non-health-losing outcome, and malformed event paths are rejected before Coordinator mutation.
  - broker_healthy becomes false before recovery; lease grant remains paused and Worker lease_count stays zero.
disproven_routes:
  - Treating process liveness as sufficient Broker health after an infrastructure-class response.
open_risks:
  - Findings 1 and 2 still require the final package/rebuild gate and controlled execute-mode simulation fault injection.
  - Findings 3 through 8 remain pending.
next_command: Commit the scoped F2 source, tests, and ledger, then start EXP-098 with a deterministic recovered-initial-gate continuation RED test.
```

## EXP-098 — Recovered initial-gate continuation verification

```yaml
experiment_id: EXP-098
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T09:34:00+08:00
  - status: RUNNING
    at: 2026-09-13T09:34:00+08:00
  - status: VALID
    at: 2026-09-13T09:37:12+08:00
prior_experiment: EXP-097
hypothesis: run() stops on the INITIAL_GATE_FAILED diagnostic even when its INVALID result was durably committed and all recovery/readmission gates succeeded, and the CLI treats that recovered diagnostic as a fatal Worker process result.
prediction: A two-point fake with only the first point gate failing will return exactly one recovered INITIAL_GATE_FAILED result and make one lease request; the CLI failure predicate will classify that recovered result as failure.
single_variable: Add only deterministic Worker-loop and CLI-exit regression tests; do not change production code in the RED phase.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 1d3de7a074c0c09875ce79e694b7019f3407bb90 with only this ledger entry uncommitted before tests
  - no live ROS, MuJoCo, MoveIt, Broker, Worker, task container, or GPU compute process
  - exact test Python and fresh NVMe scratch verified before pytest
success_criteria:
  - a successfully recovered INVALID initial-gate attempt continues to one unique remaining point and then NO_POINT
  - exactly two leases debit K for the two unique points; the final no-point request does not debit capacity
  - failed recovery remains quarantined with no second lease
  - the CLI accepts only a durably terminal recovered initial-gate result, not an unrecovered or statusless diagnostic
failure_criteria:
  - current Worker and CLI already satisfy all continuation and exit contracts
invalid_criteria:
  - import/collection failure unrelated to the deliberately absent CLI predicate, wrong overlay, reused scratch, or fake behavior that does not match the production recovery state machine
provenance:
  source_commit: 1d3de7a074c0c09875ce79e694b7019f3407bb90
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  ros_domain_id: not_applicable
  gz_partition: not_applicable
commands:
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f3r-pqBFXUst/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_worker.py::test_recovered_initial_gate_failure_continues_to_unique_remaining_point src/so101_demo_py/test/test_parallel_batch_cli.py::test_recovered_initial_gate_terminal_is_not_a_worker_process_failure src/so101_demo_py/test/test_parallel_batch_worker.py::test_failed_recovery_quarantines_and_prevents_another_lease -q
    exit_code: 1
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f3g-UbJrnxaa/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_worker.py::test_recovered_initial_gate_failure_continues_to_unique_remaining_point src/so101_demo_py/test/test_parallel_batch_cli.py::test_recovered_initial_gate_terminal_is_not_a_worker_process_failure src/so101_demo_py/test/test_parallel_batch_worker.py::test_failed_recovery_quarantines_and_prevents_another_lease -q
    exit_code: 0
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f3a-q1SDoLnu/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_worker.py src/so101_demo_py/test/test_parallel_batch_cli.py -q
    exit_code: 0
observed:
  - RED passed the existing failed-recovery quarantine control and failed both new contracts: run() returned only the recovered INITIAL_GATE_FAILED item, and the production CLI exposed no predicate capable of distinguishing recovered terminal INVALID from a fatal Worker result. Wall time was 0.59 s.
  - Focused GREEN passed all three continuation, CLI exit, and failed-recovery controls in 0.16 s pytest / 0.47 s wall.
  - Final adjacent Worker plus production CLI coverage passed 170 tests in 33.40 s pytest / 33.67 s wall.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; Worker.run now continues only when INITIAL_GATE_FAILED has completed successful recovery, while preserving the diagnostic in durable worker-results. The CLI treats that result as nonfatal only when recovered is literal true and terminal_status is the mode-correct INVALID enum. Failed recovery, missing terminal status, and every other abnormal stop remain fatal/quarantined. The two-point test proves unique P1/P2 leasing, two K debits, a final non-debit NO_POINT request, and no duplicate point.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f3r-pqBFXUst.stdout sha256=0067efc321e33ccd83c1f519d32211cb6cb158de368e8ce718856caebdb523a7
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f3g-UbJrnxaa.stdout sha256=ed0d6c079627b8413ba6fa1e9b0419bf2bb3f2c7f1917b91d9f908f1f9a678d2
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f3a-q1SDoLnu.stdout sha256=460f970aa3bd4b926f09c72cceb0295daa742520f8024fdf114e86fdb98fe48e
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f3r-pqBFXUst
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f3g-UbJrnxaa
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f3a-qMtCaD4t
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f3a-q1SDoLnu
decision: KEEP
next_experiment: EXP-099
```

```yaml
checkpoint_id: CP-085
last_valid_experiment: EXP-098
current_hypothesis: Astra finding 4 may accept an exit-zero dynamic consumer manifest solely because the path exists, without parsing or binding its terminal physical result.
working_tree_status: F3 implementation, tests, and ledger disposition are ready for one scoped commit; ignored SDD progress remains separately synchronized.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; EXP-098 started no ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process.
confirmed_conclusions:
  - Finding 3 is confirmed and fixed without weakening recovery, terminal status, or CLI failure gates.
  - Failed recovery still quarantines after exactly one lease request; recovered initial-gate INVALID continues through eligible unique work.
disproven_routes:
  - Using POINT_TERMINAL as the only continuable diagnostic even after authoritative recovery/readmission.
open_risks:
  - Findings 1 and 2 retain pending post-remediation package and live fault-injection gates.
  - Findings 4 through 8 remain pending.
next_command: Commit the scoped F3 source, tests, and ledger, then start EXP-099 with exit-zero malformed/stale/wrong-identity dynamic manifest RED cases derived from the production adapter.
```

## EXP-099 — Dynamic execution manifest verification

```yaml
experiment_id: EXP-099
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T09:40:00+08:00
  - status: RUNNING
    at: 2026-09-13T09:40:00+08:00
  - status: VALID
    at: 2026-09-13T09:45:32+08:00
prior_experiment: EXP-098
hypothesis: The production execute_result adapter maps any exit-zero regular manifest path to PASSED without parsing its content or binding it to the exact lease/session/reset/policy and physical-controller-MoveIt evidence.
prediction: Exit-zero empty, malformed, stale, and wrong-identity files will incorrectly PASS; a complete identity-bound business-failure manifest will be reduced to INDETERMINATE instead of FAILED with its actual reason.
single_variable: Add deterministic parser, producer-identity, and classification regression tests only; do not change production code in the RED phase.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit e76682158405b743aa272894a1ff0150bd5e5e07
  - one EXP-095 DONE manifest was read directly and its top-level policy, simulation, state, planning, controller reconciliation, physical sample, and Planning Scene fields were used as the compatibility shape; EXP-095 bytes remain immutable
  - no live ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process
success_criteria:
  - exit-zero empty/malformed/stale/wrong-identity manifests are INDETERMINATE and never PASSED
  - exact complete DONE maps PASSED; complete authenticated ERROR maps FAILED with its real code
  - consumer arguments and producer output carry exact batch/coordinator/worker/generation/point/attempt/lease/session/reset identity
failure_criteria:
  - current adapter already enforces all identity, provenance, terminal, and reached-stage evidence requirements
invalid_criteria:
  - import/collection failure, wrong overlay, reused scratch, or a test fixture incompatible with the directly observed EXP-095 manifest structure
provenance:
  source_commit: e76682158405b743aa272894a1ff0150bd5e5e07
  historical_manifest_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f91
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
commands:
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f4r-Px2fxXba/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_ros_runtime.py::test_exit_zero_unverifiable_dynamic_manifest_never_passes src/so101_demo_py/test/test_parallel_ros_runtime.py::test_exact_dynamic_manifest_maps_terminal_business_outcome src/so101_demo_py/test/test_parallel_worker_runtime.py::test_execute_consumer_receives_integer_reset_epoch_not_wire_label -q
    exit_code: 1
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f4g-QTqkOgIf/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_ros_runtime.py::test_exit_zero_unverifiable_dynamic_manifest_never_passes src/so101_demo_py/test/test_parallel_ros_runtime.py::test_exact_dynamic_manifest_maps_terminal_business_outcome src/so101_demo_py/test/test_parallel_worker_runtime.py::test_execute_consumer_receives_integer_reset_epoch_not_wire_label -q
    exit_code: 0
  - command: source /opt/ros/jazzy/setup.zsh; source install/mujoco_ros2_control_msgs/share/mujoco_ros2_control_msgs/package.zsh; source install/so101_mujoco_support/share/so101_mujoco_support/package.zsh; source install/so101_demo_py/share/so101_demo_py/package.zsh; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f4a-iiJ5vFe4/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_ros_runtime.py src/so101_demo_py/test/test_parallel_worker_runtime.py src/so101_demo_py/test/test_dual_cup_entrypoints.py src/so101_demo_py/test/test_dynamic_scene_sync.py -q
    exit_code: 0
observed:
  - RED collected six cases: the exact DONE control already passed, while exit-zero empty, malformed, and wrong-attempt files incorrectly PASSED; complete ERROR was INDETERMINATE; and the consumer command omitted exact lease fields. Five failed at the predicted boundaries in 0.55 s wall.
  - Focused GREEN passed all six cases in 0.14 s pytest / 0.42 s wall.
  - Final adjacent dynamic CLI/producer, ROS adapter, Worker runtime, and scene coverage passed 121 tests in 1.08 s pytest / 1.36 s wall after explicitly sourcing the local message package.
  - The preceding adjacent attempt passed 120 tests but was INVALID because test collection imported the `/opt/ros` message package rather than the worktree message overlay; it is retained only as a deletion candidate.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; the dynamic consumer now receives and persists all seven exact lease fields. The parent reads a bounded owner-matched regular file through O_NOFOLLOW, rejects mutation during read, and independently binds lease, Worker session, reset epoch, and installed dynamic policy identity. DONE additionally requires coherent exit/state/trace/release, controller/joint, physical reset, planning, and detached Planning Scene evidence. A complete bound ERROR with the same reached-stage evidence maps to FAILED with its real failure code; absent or unverifiable evidence remains INDETERMINATE. The directly observed EXP-095 DONE schema supplied the derived compatibility fixture shape without modifying historical evidence.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f4r-Px2fxXba.stdout sha256=dfdb51d0c53d891bf37015465f08516af9cf904622e8204f431fa6ff1ac06cd0
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f4g-QTqkOgIf.stdout sha256=90938eb99f6e9883d2cea26507b9cf7d10939651a834da1233047d54adfdb5a4
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f4a-iiJ5vFe4.stdout sha256=53ee2ffb9ffc713914f78d8e370d831996313d1c2467f5d8ff69b84238f189b2
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f4r-Px2fxXba
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f4g-QTqkOgIf
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f4a-Eq2CYrVr
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f4a-iiJ5vFe4
decision: KEEP
next_experiment: EXP-100
```

```yaml
checkpoint_id: CP-086
last_valid_experiment: EXP-099
current_hypothesis: Astra finding 5 may allow a PASSED sealed result to omit verifier-owned reset, initial, pose, execution, controller/TF/joint, MuJoCo, Planning Scene, and visual evidence by declaring only attempt-result.json as required.
working_tree_status: F4 implementation, tests, and ledger disposition are ready for one scoped commit; ignored SDD progress remains separately synchronized.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; EXP-099 started no ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process.
confirmed_conclusions:
  - Finding 4 is confirmed and fixed at both producer identity and parent verification/classification boundaries.
  - Historical EXP-095 remains immutable and is not claimed as post-fix qualification.
disproven_routes:
  - Treating process exit zero plus path existence as physical PASS authority.
open_risks:
  - F4 requires the final rebuilt overlay and live qualification because historical manifests intentionally lack the new exact lease field.
  - Findings 5 through 8 remain pending.
next_command: Commit the scoped F4 producer, parser, tests, and ledger, then start EXP-100 with a self-consistent PASSED seal that omits verifier-owned stage evidence.
```

## EXP-100 — Verifier-owned sealed evidence contract

```yaml
experiment_id: EXP-100
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T09:50:00+08:00
  - status: RUNNING
    at: 2026-09-13T09:50:00+08:00
  - status: VALID
    at: 2026-09-13T09:57:21+08:00
prior_experiment: EXP-099
hypothesis: A producer can publish a self-consistent PASSED seal with required=[attempt-result.json] while omitting reset-bound initial, pose, numeric, dynamic execution, controller, Planning Scene, and terminal visual evidence, because verification trusts the producer-owned required list.
prediction: A PASSED seal with a complete inventory but one verifier-required artifact omitted, or with wrong POSE/dynamic lease identity, will be accepted by the current verifier when the producer declares only the result file.
single_variable: Add deterministic artifact omission and identity-binding regression tests only; do not change production code in the RED phase.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit d91298422a779ca4d27ea07eea87ed5cc730fcaf
  - EXP-095 attempt manifest was read directly and confirmed to declare only attempt-result.json while retaining richer evidence; its bytes remain immutable
  - no live ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process
success_criteria:
  - PASSED execute and VALIDATION_PASSED plan-only seals use verifier-owned requirements that producer declarations cannot weaken
  - stage-complete evidence binds exact attempt or validation identity, reset/session, POSE, numeric TF/physical, planning or dynamic controller/physical/Planning Scene content, and initial/terminal visual artifacts
  - producer-declared supersets remain allowed; incomplete and wrong-identity seals fail closed
failure_criteria:
  - current verification already enforces the complete independent contract
invalid_criteria:
  - import/collection failure, wrong overlay, reused scratch, or a fixture incompatible with the directly observed EXP-095 schema
provenance:
  source_commit: d91298422a779ca4d27ea07eea87ed5cc730fcaf
  historical_manifest_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f91
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
commands:
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5r-sAIUZ2hs/tmp /usr/bin/python3 -m pytest -p no:cacheprovider <11 focused verifier-owned omission/identity/superset cases> -q
    exit_code: 1
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5g-X2u8w8Q4/tmp /usr/bin/python3 -m pytest -p no:cacheprovider <12 focused execute and plan-only verifier-owned evidence cases> -q
    exit_code: 0
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5a-ujOtAZmX/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_artifacts.py src/so101_demo_py/test/test_parallel_batch_cli.py -q
    exit_code: 0
observed:
  - The valid RED collected 11 cases. All eight PASSED omission cases and both wrong-identity cases were accepted by the old verifier; only the complete producer-superset control passed. Wall time was 0.66 s.
  - Focused GREEN passed all 12 execute/plan-only cases in 0.26 s pytest / 0.58 s wall.
  - Final adjacent artifact and production CLI coverage passed 163 tests in 32.18 s pytest / 32.47 s wall.
  - An earlier collection-only attempt lacked the worktree overlay and exited 2 before importing so101_demo; it is INVALID and retained only as a deletion candidate.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; sealing and readback now independently compute a cumulative evidence stage and verifier-owned required set. PASSED execute requires reset-bound initial/inference images, exact POSE identity, depth/TF/session/reset physical evidence, a terminal visual, and an exact dynamic lease receipt with planning, controller/joint, MuJoCo sample, outcome, and detached Planning Scene evidence. Plan-only PASS has a distinct persisted planning-receipt contract; dry-run remains scheduler-only. Producer declarations may add requirements but cannot remove verifier requirements. Historical EXP-095 bytes were not rewritten and are not claimed as post-fix qualification.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f5r-sAIUZ2hs.stdout sha256=170dd7d6deae2426fbc250e880ebc4ce9cae524f05205a965a30b8de7a65a019
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f5g-X2u8w8Q4.stdout sha256=ccc03f184f820f021127453e09e83d55e026e6b17aee2b49425353b0adb000c2
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f5a-ujOtAZmX.stdout sha256=e09dcd44d901c37b2e20c1a0d198077ac6b9a68fd6db167f17cb9ee4cc184a35
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5r-I65KRMWM
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5r-sAIUZ2hs
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5g-Xl5OmcEt
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5a-gYDlJly5
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5a-U1L6uSv5
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5g-X2u8w8Q4
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f5a-ujOtAZmX
decision: KEEP
next_experiment: EXP-101
```

```yaml
checkpoint_id: CP-087
last_valid_experiment: EXP-100
current_hypothesis: Astra finding 6 may make Coordinator crash recovery unreachable from the production CLI because duplicate-root rejection and fresh allocation occur before journal replay.
working_tree_status: F5 implementation, tests, and ledger disposition are ready for one scoped commit; ignored SDD progress remains separately synchronized.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; EXP-100 started no ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process.
confirmed_conclusions:
  - Finding 5 is confirmed and fixed with verifier-owned run-mode/status/stage requirements and exact evidence identity/content binding.
  - Historical EXP-095 evidence remains byte-for-byte immutable and cannot silently acquire the hardened contract.
disproven_routes:
  - Treating a producer-declared required list and a self-consistent tree hash as sufficient evidence for PASSED.
open_risks:
  - Findings 1 through 5 retain pending final rebuilt-overlay and live gates.
  - Findings 6 through 8 remain pending.
next_command: Commit the scoped F5 artifact contract, CLI planning receipt, tests, and ledger, then start EXP-101 by verifying the production crash-resume design and CLI reachability.
```

## EXP-101 — Production Coordinator crash-resume reachability

```yaml
experiment_id: EXP-101
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:02:00+08:00
  - status: RUNNING
    at: 2026-09-13T10:02:00+08:00
  - status: VALID
    at: 2026-09-13T10:13:15+08:00
prior_experiment: EXP-100
hypothesis: Journal replay and conservative in-flight adjudication exist, but the production CLI cannot reach them because it rejects an existing evidence root before provenance verification and composition always performs fresh resource allocation.
prediction: An explicit --resume invocation against an exact frozen two-point dry-run batch will fail at argument/root preparation instead of acquiring a new Coordinator epoch, settling the started lease, rotating the Worker generation, and continuing the remaining point.
single_variable: Add only an explicit CLI recovery/crash-window test and exact old-process retirement contract; do not change production code in the RED phase.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 1f447581b7ade0de52fc95fbb21c25c05d1ec107
  - frozen design section 12 explicitly requires Coordinator restart, epoch rotation, journal replay, sealed-result adjudication, and conservative handling of authorized starts
  - no live ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process
success_criteria:
  - fresh mode still rejects every existing evidence root before provenance side effects
  - explicit resume requires an existing exact batch manifest and current matching frozen inputs/provenance
  - recovery acquires the original journal lock, fences exact old owned identities, reclaims unchanged resources, rotates credentials/generations, and continues only eligible points
  - an already STARTED dry-run validation is conservatively settled without any physical runtime, while the untouched second point continues once
failure_criteria:
  - production CLI already exposes and completes the explicit safe recovery path
invalid_criteria:
  - wrong overlay, reused scratch, malformed synthetic history, or any physical process startup in the dry-run recovery test
provenance:
  source_commit: 1f447581b7ade0de52fc95fbb21c25c05d1ec107
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
commands:
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6r-bh42z0fC/tmp /usr/bin/python3 -m pytest -p no:cacheprovider <explicit dry-run resume and exact process-manifest retirement RED> -q
    exit_code: 1
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6g-S4n0TZJG/tmp /usr/bin/python3 -m pytest -p no:cacheprovider <six focused fresh/recovery/fencing/replay cases> -q
    exit_code: 0
  - command: TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6a-YZdun5pM/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_cli.py src/so101_demo_py/test/test_parallel_batch_coordinator.py src/so101_demo_py/test/test_parallel_batch_resources.py src/so101_demo_py/test/test_parallel_processes.py -q
    exit_code: 0
observed:
  - Valid RED failed both target cases: --resume was not recognized, and ProcessSupervisor exposed no exact prior-manifest retirement operation. Wall time was 0.61 s.
  - Focused GREEN passed six fresh-root, frozen-manifest, dry-run crash-window, validation replay, exact retirement, and PID-reuse rejection cases in 1.49 s pytest / 1.77 s wall.
  - Final adjacent CLI, Coordinator, resource allocator, and process supervisor coverage passed 340 tests in 36.65 s pytest / 36.92 s wall.
  - The dry-run crash window durably STARTED task_start under epoch 1, closed the owner, then resumed under epoch 2. It conservatively recorded task_start VALIDATION_INVALID, rotated worker-01 to generation 2, executed sample_01_near_left exactly once as VALIDATION_PASSED, retained both physical PointStatus values UNRUN, and emitted no ATTEMPT_STARTED event.
  - Earlier runs with an overlong socket fixture, a syntax typo, a post-close test replay, and two incomplete test expectation updates were INVALID or intermediate and are retained only as deletion candidates.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; the frozen design requires Coordinator restart and the production CLI now exposes it only through explicit --resume. Fresh mode still rejects existing roots before provenance. Resume requires an owner-private existing root, absence of a finalized root aggregate, exact current frozen batch/provenance equality, exclusive journal lock/new epoch, exact prior process fencing, strict resource/environment re-admission, conservative old-lease adjudication, and Worker generation/session/token rotation before eligible work continues. Physical Broker recovery additionally selects a new broker generation and uses the existing exact container identity/label/mount retirement gate. No gate was weakened and the controlled recovery proof was scheduler-only.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f6r-bh42z0fC.stdout sha256=216ec33b840f0634472509f81fe934c093252f195598e7109d89ad9f796146d4
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f6g-S4n0TZJG.stdout sha256=9187cef6d5d8364b3a1da07505cbe8ac7279e04991ed4f2120cbad5cbb5e8d1b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f6a-YZdun5pM.stdout sha256=d3358927456977fd781e9b42ecdf3445640fd73b3b661bad5e4d242dfc71843e
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6r-uPeMvVkV
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6r-bh42z0fC
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6g-QWMJaFya
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6g-iFAoWwoE
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6a-nIW4TTCj
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6a-Qk1mcgYG
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6g-e0cTXxis
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6g-LcZIMlfk
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6g-S4n0TZJG
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f6a-YZdun5pM
decision: KEEP
next_experiment: EXP-102
```

```yaml
checkpoint_id: CP-088
last_valid_experiment: EXP-101
current_hypothesis: Astra finding 7 may advertise supported N=3 while the CLI has no way to provide the mandatory accepted Task-14 live-headroom evidence to the allocator.
working_tree_status: F6 implementation, tests, and ledger disposition are ready for one scoped commit; ignored SDD progress remains separately synchronized.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; EXP-101 used only in-process dry-run fakes and started no ROS, MuJoCo, MoveIt, Broker, Worker child, container, or GPU process.
confirmed_conclusions:
  - Finding 6 is confirmed and fixed through an explicit fail-closed recovery entry point rather than weakening duplicate-root rejection.
  - Exact process identity and frozen input/provenance mismatches prevent recovery before new authorization.
disproven_routes:
  - Relying on latent CoordinatorJournal replay while the production CLI remains fresh-root-only.
open_risks:
  - Findings 1 through 6 retain pending final rebuilt-overlay and live gates.
  - Findings 7 and 8 remain pending.
next_command: Commit the scoped F6 recovery implementation/tests/ledger, then start EXP-102 with the N=3 CLI capability contract.
```

## EXP-102 — Production three-Worker headroom evidence wiring

```yaml
experiment_id: EXP-102
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:18:12+08:00
  - status: RUNNING
    at: 2026-09-13T10:18:12+08:00
  - status: VALID
    at: 2026-09-13T10:22:20+08:00
prior_experiment: EXP-101
hypothesis: The frozen runtime configuration advertises max_worker_count=3 and the allocator enforces accepted Task-14 headroom, but the production batch CLI cannot supply the candidate, independent controller acceptance, and current provenance inputs to that verifier.
prediction: A production N=3 invocation cannot compose successfully with valid accepted evidence, while the CLI exposes no fail-closed distinction among absent, stale, and forged evidence.
single_variable: Add deterministic production-CLI N=3 capability tests only; do not change production code in the RED phase.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 8863cac2233e9f8be8036c5de006220d9b431ec6
  - config/mujoco/parallel_batch_v1.yaml advertises max_worker_count 3 and three ROS domain IDs
  - WorkerResourceAllocator requires Task14LiveHeadroomVerifier for N=3 and does not downgrade admission
  - no live ROS, MuJoCo, MoveIt, Broker, Worker child, container, or GPU process
success_criteria:
  - CLI N=3 requires all three independent absolute inputs and binds the verified identity into its frozen batch manifest
  - valid current accepted evidence reaches real ProductionBatchComposition and allocates exactly three Workers
  - absent, stale-current-provenance, and forged-controller-acceptance cases fail closed before Worker or Broker startup
  - N=1/N=2 reject stray headroom arguments and unchanged N=2 behavior remains admitted without Task-14 evidence
failure_criteria:
  - production CLI already securely exposes and composes all required Task-14 authorities
invalid_criteria:
  - import/collection failure, wrong overlay, reused scratch, synthetic verifier bypass, or any live process startup
provenance:
  source_commit: 8863cac2233e9f8be8036c5de006220d9b431ec6
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
commands:
  - command: source the four worktree overlays; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f7r-Mkb3QQZA/tmp /usr/bin/python3 -m pytest -p no:cacheprovider <four production N=3 valid/absent/stale/forged CLI cases> -q
    exit_code: 1
  - command: source the four worktree overlays; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f7g-rpF1mDtJ/tmp /usr/bin/python3 -m pytest -p no:cacheprovider <four production N=3 valid/absent/stale/forged CLI cases> -q
    exit_code: 0
  - command: source the four worktree overlays; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f7a-OM6zbIxS/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_cli.py src/so101_demo_py/test/test_parallel_batch_resources.py -q
    exit_code: 0
observed:
  - The valid RED collected all four cases and failed at the predicted boundary: all three authority arguments were unrecognized, while an N=3 request without them passed preparation. Wall time was 0.82 s.
  - Focused GREEN passed the four real Task-14 verifier cases in 0.22 s pytest / 0.48 s wall.
  - Final adjacent CLI/resource coverage, including the N=2 unexpected-authority rejection, passed 199 tests in 32.75 s pytest / 33.03 s wall.
  - One earlier collection attempt without sourcing the worktree overlay exited 2 and is INVALID; it is retained only as a deletion candidate.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; max_worker_count=3 remains an advertised capability, but production now requires all three independent inputs: the sealed Task-14 candidate, controller-owned acceptance outside the candidate tree, and a deterministic eight-file current-provenance root. Preparation verifies and freezes the complete result, composition re-verifies it, and fresh allocation verifies it again before resource creation. Resume re-verifies before exact frozen-manifest comparison. Missing, stale, forged, changed, partial, relative, or N-not-3 unexpected authority fails closed; the allocator admission policy is unchanged.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f7r-Mkb3QQZA.stdout sha256=7feb7f81a7e8cab7cb5e028a707ce9dff033a1978844ddd2af8a8e5175a53f67
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f7g-rpF1mDtJ.stdout sha256=44178be163015033384cffd8b0f0ec02d28cb6648af3d8dbe3121b41f45ca4aa
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f7a-OM6zbIxS.stdout sha256=cc7fbc2c050a2c370572fb2755e3683ea202a865239d673fd94d369a856d0c2c
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f7r-cjQmlxdT
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f7r-Mkb3QQZA
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f7g-rpF1mDtJ
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f7a-OM6zbIxS
decision: KEEP
next_experiment: EXP-103
```

```yaml
checkpoint_id: CP-089
last_valid_experiment: EXP-102
current_hypothesis: Astra finding 8 remains as a recovery-index consistency defect after the behavioral findings are fixed; the ledger header and SDD summary must identify CP-089/EXP-102 before the final package and runtime qualification sequence.
working_tree_status: F7 implementation, tests, and ledger disposition are ready for one scoped commit; ignored SDD progress remains separately synchronized.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; EXP-102 used only in-process dry-run composition and started no ROS, MuJoCo, MoveIt, Broker child, Worker child, container, or GPU process.
confirmed_conclusions:
  - Finding 7 is confirmed and fixed without bypassing Task-14 acceptance, current provenance, resource admission, or resume identity gates.
  - N=2 rejects rather than silently ignores supplied three-Worker authority.
disproven_routes:
  - Treating the allocator's unwired default verifier as a reachable production N=3 capability.
open_risks:
  - Findings 1 through 7 retain pending final rebuilt-overlay and live gates.
  - Finding 8 and all mandatory final verification remain pending.
next_command: Re-read and synchronize the ledger header and ignored SDD progress, add the lightweight recovery-index consistency test, verify F7 evidence hashes directly, and commit the scoped F7 fix before F8.
```

## EXP-103 — Ledger and SDD recovery-index consistency

```yaml
experiment_id: EXP-103
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:24:30+08:00
  - status: RUNNING
    at: 2026-09-13T10:24:30+08:00
  - status: VALID
    at: 2026-09-13T10:26:03+08:00
prior_experiment: EXP-102
hypothesis: The ledger header and SDD recovery summary can drift behind the monotonically appended body because no automated check binds the header checkpoint and next experiment to the highest body records.
prediction: A lightweight consistency test will fail against the current stale CP-086/EXP-100 header while the body reaches CP-089/EXP-103 RUNNING.
single_variable: Add the recovery-index consistency test only before synchronizing the ledger header and SDD state.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 4c141338805a230cb005e009bf0f9f42ad2bb6bf
  - EXP-102 and CP-089 are durable in the ledger
  - no live ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process
success_criteria:
  - the header latest_checkpoint equals the numerically highest checkpoint in the body
  - next_experiment equals the highest RUNNING experiment or the successor of the highest terminal experiment
  - current_commit is a complete 40-hex source commit and SDD identifies the same remediation boundary
failure_criteria:
  - the existing header is already consistent and no regression guard is needed
invalid_criteria:
  - import/collection failure, wrong overlay, reused scratch, or a test that rewrites the ledger
provenance:
  source_commit: 4c141338805a230cb005e009bf0f9f42ad2bb6bf
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
commands:
  - command: source the four worktree overlays; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f8r-hZZPih7m/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_ledger.py -q
    exit_code: 1
  - command: source the four worktree overlays; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f8g-qTLWh1gI/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_ledger.py -q
    exit_code: 0
  - command: source the four worktree overlays; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f8a-XveWJTpF/tmp /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_parallel_batch_ledger.py -q
    exit_code: 0
observed:
  - RED failed exactly because the header advertised CP-086 while the body reached CP-089; the same stale header still advertised EXP-100 while EXP-103 was RUNNING.
  - GREEN passed after the header identified source commit 4c141338805a230cb005e009bf0f9f42ad2bb6bf, CP-089, and EXP-103, and the ignored SDD recovery summary named the same boundary.
  - Final terminal-state readback also passed after advancing the header/body together to CP-090 and next EXP-104.
  - The guard derives the highest checkpoint and highest experiment status from the body, so a terminal experiment requires its successor while PLANNED/RUNNING requires the current experiment.
inferred:
  - NONE
conclusion: CONFIRMED_AND_FIXED; the stale ledger/SDD recovery index is synchronized without rewriting any historical record, and the new read-only test prevents checkpoint/next-experiment drift while requiring a full 40-hex source commit.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f8r-hZZPih7m.stdout sha256=18b99761b9b8fe2b5d4ed2e53aaa8f3ffbabccb15aedfea2585e363762387d02
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f8g-qTLWh1gI.stdout sha256=4bcefcc9f6c645923b9993ccf73ad92e6b400ca25458ea14e095857fc2131342
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-remediate-f8a-XveWJTpF.stdout sha256=4bcefcc9f6c645923b9993ccf73ad92e6b400ca25458ea14e095857fc2131342
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f8r-hZZPih7m
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f8g-qTLWh1gI
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f8a-XveWJTpF
decision: KEEP
next_experiment: EXP-104
```

```yaml
checkpoint_id: CP-090
last_valid_experiment: EXP-103
current_hypothesis: All eight Astra findings are now dispositioned in code and focused/adjacent tests; the complete affected package suite is the next gate before rebuild, execute fault injection, and fresh qualification.
working_tree_status: F8 ledger-header guard and synchronized recovery metadata are ready for one scoped commit; ignored SDD progress remains synchronized separately.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; EXP-103 was a read-only document consistency test and started no runtime process.
confirmed_conclusions:
  - Finding 8 is confirmed and fixed without changing historical experiment facts or hashes.
  - Findings 1 through 8 have deterministic RED/GREEN and adjacent evidence; none is being claimed runtime-qualified yet.
disproven_routes:
  - Manually updating only the ledger body or only the SDD without a header/body consistency guard.
open_risks:
  - Complete package, rebuilt overlay/provenance, execute heartbeat fault, execute live-unhealthy Broker fault, fresh four-point, fresh twenty-point, visual inspection, cleanup, and independent Astra high review remain mandatory.
next_command: Re-run the ledger consistency guard in its terminal CP-090/EXP-104 state, verify all referenced hashes directly, and commit F8 before preregistering the complete package gate as EXP-104.
```

## EXP-104 — Complete post-remediation package and overlay gate

```yaml
experiment_id: EXP-104
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:28:54+08:00
  - status: RUNNING
    at: 2026-09-13T10:28:54+08:00
  - status: VALID
    at: 2026-09-13T10:36:35+08:00
prior_experiment: EXP-103
hypothesis: The complete remediation through F8 builds in the four-package worktree overlay and passes the full ordinary so101_demo_py package suite with the locked ML dependency path, zero errors, failures, or skips, and no benchmark collection.
single_variable: Replace the prior F91 source with current remediation source 01a16914a0580b944b10cd16803f32a7c39cd76f; do not start live runtime or change config, catalog, models, or Broker policy.
lifecycle: ISOLATED_STACK
preconditions:
  - source commit 01a16914a0580b944b10cd16803f32a7c39cd76f; submodule c16b5a5fe880b6e1857f56486dab4ae726576969
  - no related ROS, MuJoCo, MoveIt, Broker, Worker, container, or GPU process
  - 232 GiB free on /data; fresh short NVMe scratch required for build/test
success_criteria:
  - four selected worktree packages build with --symlink-install from the Jazzy underlay
  - the exact test interpreter resolves tempfile inside the fresh scratch
  - colcon test and scoped test-result both exit zero with no errors, failures, or skips
  - no benchmark_test is collected and installed/runtime paths resolve to this worktree
failure_criteria:
  - any build/test/test-result failure or stale/mixed installed path blocks live work
invalid_criteria:
  - reused/long/non-NVMe scratch, locked ML path injected during build, wrong overlay, or unscoped stale test-result
provenance:
  source_commit: 01a16914a0580b944b10cd16803f32a7c39cd76f
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runner_python: /usr/bin/python3
  locked_site_packages: /data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages
intermediate_observed:
  - The four-package p116 symlink build passed in 2.49 s.
  - The first complete p117 package test validly collected 2839 tests and exposed four crash-publication fixture regressions after 2835 passes: those fixtures claimed PASSED with only attempt-result.json, which the F5 verifier correctly rejects because no physical execution evidence exists.
  - The fixtures now use a truthful reset-stage INVALID seal while retaining the same before/after fsync, atomic rename, recovery-discovery, durable RESULT_COMMITTED, and late-result assertions. Focused p119 passed all five cases. The intermediate p118 collection error used the nonexistent PointStatus.INVALID and is INVALID harness evidence only.
intermediate_evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p117-colcon-test.log sha256=1dc2e10cc9e309b6791f49bfc8aad27554a1c3993d5ed91c3df0c1db863b8633
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p119-crash-fixture-green.stdout sha256=9f5fca75b3047a6b50338570acc3b84d6f91fc01f7616bf565c9c7f9222d4381
intermediate_deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p116
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p117
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p118
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p119
commands:
  - command: source /opt/ros/jazzy/setup.zsh; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p120/tmp /usr/bin/python3 -m colcon build --packages-select mujoco_ros2_control_msgs so101_mujoco_support so101_teleop so101_demo_py --symlink-install
    exit_code: 0
  - command: source the four worktree overlays; prepend locked ML site-packages; TMPDIR=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p121/tmp /usr/bin/python3 -m colcon test --packages-select so101_demo_py --event-handlers console_direct+ --return-code-on-test-failure
    exit_code: 0
  - command: /usr/bin/python3 -m colcon test-result --test-result-base build/so101_demo_py --all --verbose
    exit_code: 0
observed:
  - Fresh source commit a6434abd9e9aa9c992c81eed45f28bf015e753c7 built all four selected packages with --symlink-install in 2.48 s.
  - The exact /usr/bin/python3 test interpreter resolved tempfile to p121/tmp and imported torch 2.13.0+cu130, MuJoCo 3.12.0, ROS Jazzy, and so101_demo from this worktree build.
  - The complete ordinary package suite passed 2839 tests in 84.73 s pytest / 86.44 s wall; scoped test-result reports 0 errors, 0 failures, and 0 skips. The two names containing the word benchmark are partition/config contract tests; no benchmark runner was collected.
conclusion: VALID; the complete affected overlay and ordinary package gate pass after correcting the nonphysical crash fixture. No runtime stack or container was started by this experiment.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p120-colcon-build.log sha256=6520ac31c2e864f989333a593b7a1047c6115bc328c5a4fd64decd70cf342e5c
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p121-colcon-test.log sha256=fc3f8d74930de6a6151acbf2fffe6276352c89d41b8c6e2ad8d0dc76a5b7272e
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p121-colcon-test-result.log sha256=4b625d83a538e183a2d37077cb94c17199f640f53922904ccaff238841bac644
  - /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/build/so101_demo_py/pytest.xml sha256=9e308d15cd968ac906dfb69efcfc343694fe0bd6b05060b579138f355733cff3
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p120
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p121
decision: KEEP
next_experiment: EXP-105
```

```yaml
checkpoint_id: CP-091
last_valid_experiment: EXP-104
current_hypothesis: The passing rebuilt overlay can produce source/install/runtime/image provenance and a fresh dual-model smoke before live execute fault injection.
working_tree_status: EXP-104 result and CP-091 are ledger-only; runtime source is clean at a6434abd9e9aa9c992c81eed45f28bf015e753c7 and ignored SDD progress is synchronized separately.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; package tests left no live runtime process or container.
confirmed_conclusions:
  - Complete four-package build and 2839-test ordinary suite pass with zero errors/failures/skips.
  - Hardened verifier contract remains unchanged; only a test fixture stopped fabricating unsupported PASSED evidence.
open_risks:
  - Static source/install/runtime/image provenance, smoke, both execute fault injections, fresh four-point/full qualification, visual inspection, cleanup, and final Astra review remain pending.
next_command: Commit EXP-104/CP-091 ledger state, preregister EXP-105, then generate direct source/install/runtime provenance and rebuild/smoke the immutable Broker image.
```

## EXP-105 — Post-remediation provenance, immutable image, and model smoke

```yaml
experiment_id: EXP-105
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:37:53+08:00
  - status: RUNNING
    at: 2026-09-13T10:37:53+08:00
  - status: VALID
    at: 2026-09-13T10:40:08+08:00
prior_experiment: EXP-104
hypothesis: The clean post-remediation checkout and freshly built overlay have exact source/install/entrypoint provenance and can rebuild one immutable Broker image whose internal verified source equals the host source, then execute both frozen models successfully.
single_variable: Qualify source/install/image bytes from clean remediation source; do not start a Worker, MoveIt, controller, or physical simulation stack.
lifecycle: ISOLATED_STACK
preconditions:
  - complete package gate EXP-104 VALID
  - clean git HEAD de080f20ed2c09f20a043415aa4fe654d470e89d; runtime/test source through a6434abd9e9aa9c992c81eed45f28bf015e753c7
  - no related process/container/GPU application and exact model input hashes unchanged
success_criteria:
  - direct source/install/console/config/catalog/model identities pass production verify_provenance
  - image build receipt, docker inspect labels, and image-internal provenance agree exactly
  - YOLO and Grounded-SAM each return one QUALIFIED candidate from the frozen smoke input
  - smoke container is removed and no GPU/container residue remains
failure_criteria:
  - any dirty/mixed overlay, hash mismatch, model failure, mutable image identity, or residual state blocks execute fault tests
invalid_criteria:
  - reused output/root, wrong model path, existing container endpoint, or incomplete resource preflight
provenance:
  source_commit: de080f20ed2c09f20a043415aa4fe654d470e89d
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
commands:
  - command: source the four worktree overlays; scripts/parallel-perception-container.sh build --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --output reports/remediation-image-build-105.json
    exit_code: 0
  - command: source the four worktree overlays; scripts/parallel-perception-container.sh smoke --image-id sha256:beae4e2cfdf5e971c8be078b0ee36af1232a414b027e1cd1971f609ea1869681 --batch-root task14-remediation-105-smoke --input <frozen smoke image> --yolo-weights <frozen YOLO> --grounded-root <frozen Grounded-SAM> --output reports/remediation-smoke-admission-105.json
    exit_code: 0
  - command: production verify_provenance with exact catalog/config/model/image inputs and worktree libexec PATH
    exit_code: 0
observed:
  - The immutable image rebuilt in 13.46 s. Build receipt, Docker labels, and image-internal readback all bind image sha256:beae4e2cfdf5e971c8be078b0ee36af1232a414b027e1cd1971f609ea1869681 to source hash f6195235857c6f956ef28943dda044d9b80ff84ee1eb76132be9f77473167663.
  - Fresh smoke completed in 9.99 s: plastic-cup-yolo11n-seg-v1 returned one QUALIFIED candidate in 34.7966 ms and Grounded-SAM returned one QUALIFIED candidate in 199.1376 ms.
  - Production verify_provenance resolved clean source commit a65e96c851ad9b4f5ae10864c701b86672c59862, exact source/image hash f6195235857c6f956ef28943dda044d9b80ff84ee1eb76132be9f77473167663, equal source/install module tree hash 5956958e7a3fa4bebb492ed45ab6f13c39a4fbbbaecf0b49ab301d50c21aa143, and the worktree console/module/config/catalog/model paths.
  - Post-smoke audit found no related process, running container, or GPU compute application.
conclusion: VALID; source, install, runtime entrypoint, immutable image, both model executions, and cleanup are qualified for controlled simulation fault injection.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p123-image-build.log sha256=f16edd7ac5c30b4566f8bc56cd5de3237618c67bc9e5276cf92d53df0c5f85f6
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p124-model-smoke.log sha256=f80122cfa5f1bdd5c550b15ed7bb1d67b0cd49f3c9d58a6f8a3857895ebda4d6
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-production-provenance-105.json sha256=20557c54ae9f1ab59d4585abed9e90ab398c794b993cf8bc57a017461f409e28
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-image-build-105.json sha256=0cc3bee433882d28387c225d18234c4ee2cc0aba2ad2758eda06eb61856cff96
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-smoke-admission-105.json sha256=71e4abed0210452dd2401f6147d0f7554210b4170bb41cd704fbea24f88cb72d
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-remediation-105-smoke/ipc/smoke.json sha256=e20224b09549d09c1e71363711647f2379b5ca128aedb3eae4bdd7e05054b41e
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-105-cleanup-audit.json sha256=27b575ecbbc39d8172d555b9d364e4d44d5bf7f2df740292d288886de61fea3f
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p123
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p124
decision: KEEP
next_experiment: EXP-106
```

```yaml
checkpoint_id: CP-092
last_valid_experiment: EXP-105
current_hypothesis: The rebuilt execute runtime cancels and confirms the exact in-flight controller work while its normal execution call remains blocked after heartbeat/lease revocation, with no subsequent goal and conservative result classification.
working_tree_status: EXP-105 result and CP-092 are ledger-only; clean source/image provenance is qualified at a65e96c851ad9b4f5ae10864c701b86672c59862.
owned_processes: NONE
preserved_processes: tmux session codex belongs to the active coding task; smoke container was removed and GPU/process audits are empty.
confirmed_conclusions:
  - Static, installed, runtime, image, dual-model, and cleanup gates pass for the current remediation source.
open_risks:
  - Execute heartbeat/lease-loss fault, alive-unhealthy Broker fault, fresh four-point/full qualification, visual inspection, cleanup, and final Astra review remain pending.
next_command: Commit EXP-105/CP-092, preregister EXP-106, and run the controlled execute-mode heartbeat/lease revocation fault with exact controller/joint/TF/MuJoCo/MoveIt/visual/process evidence.
```

## EXP-106 — Execute heartbeat/lease-revocation fault injection

```yaml
experiment_id: EXP-106
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:44:27+08:00
  - status: RUNNING
    at: 2026-09-13T10:44:27+08:00
  - status: INVALID
    at: 2026-09-13T10:47:12+08:00
prior_experiment: EXP-105
hypothesis: When the Coordinator becomes unavailable while the exact dynamic consumer is executing, the Worker watchdog independently revokes that lease, fences later goals, cancels and confirms the current controller goal within the heartbeat bound, and leaves MuJoCo and Planning Scene conservatively recoverable.
prediction: Suspending only the exact manifest-owned Coordinator process after a dynamic execute consumer appears will block heartbeat acknowledgement while leaving the Worker alive; before Coordinator resume, the exact consumer/controller work will be stopped, and after resume no later goal from the revoked lease will be submitted.
single_variable: Suspend and resume only the exact Coordinator process during one execute attempt; source, install, immutable image, models, config, catalog point, and safety gates remain EXP-105-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v1-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-106
worker_count: 1
max_points_per_worker: 1
selection: task_start
fault_sequence:
  - wait for the exact Worker-owned dynamic consumer and an in-flight controller action
  - capture exact Coordinator/Worker/consumer/controller identity plus pre-fault joint, TF, MuJoCo and Planning Scene state
  - SIGSTOP only the exact Coordinator identity for longer than heartbeat_timeout_s
  - require Worker-side revocation, exact consumer termination, controller cancellation and no active goal before SIGCONT
  - resume the same Coordinator identity and require conservative adjudication, cleanup and no subsequent revoked-lease goal
success_criteria:
  - exact identity checks pass before both signals
  - cancellation and no-active-goal evidence is produced while the Coordinator and normal execution path remain blocked
  - no later goal is submitted for the revoked lease
  - controller/joint/TF, MuJoCo physical, Planning Scene, process ownership and fresh visual evidence are complete and internally consistent
  - exact cleanup leaves no owned process, task container, GPU process or active controller goal
failure_criteria:
  - cancellation waits for Coordinator resume or dynamic execution return
  - a stale/different identity is signalled, a later revoked goal appears, physical state is uncertain without conservative failure, or cleanup/evidence is incomplete
invalid_criteria:
  - the fault misses the active dynamic execute window, the Coordinator identity changes before signal, the root exists before launch, or source/install/image provenance is mixed
provenance:
  source_commit: d9b141bedcc73d7975f1fae1a4722653e532eeba
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:beae4e2cfdf5e971c8be078b0ee36af1232a414b027e1cd1971f609ea1869681
observed:
  - The launch shell enabled nounset before sourcing ROS setup files. Those setup files legitimately read unset tracing/prefix variables, so the overlay did not populate the package metadata path.
  - The console process exited 1 in 0.128845 s with PackageNotFoundError before allocating the batch root; no Broker, Worker, ROS, MuJoCo, MoveIt, controller, container, GPU process, lease or physical action existed.
conclusion: INVALID orchestration environment; this is not heartbeat-fault or product evidence, and its experiment and batch IDs will not be reused.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-106.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-106.time
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-106.exit
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/coordinator-identity-106.json
retention_rule: Retain all fault, command, runtime, numeric, visual and cleanup evidence; delete nothing without explicit user authorization.
decision: KEEP_INVALID
next_experiment: EXP-107
```

```yaml
checkpoint_id: CP-093
last_valid_experiment: EXP-105
current_hypothesis: The heartbeat fault hypothesis remains untested because EXP-106 failed before product startup; removing only shell nounset and using a new root should reach the preregistered in-flight fault window.
working_tree_status: EXP-106 invalid launch evidence is ledger-only; no runtime root or product-owned process was created.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - EXP-106 is an orchestration invalid caused by overlay setup under nounset, not a product result.
open_risks:
  - The complete execute heartbeat/lease-loss fault gate remains pending.
next_command: Preregister EXP-107 with a new batch/root and rerun the otherwise identical fault sequence without shell nounset.
```

## EXP-107 — Execute heartbeat/lease-revocation fault injection retry

```yaml
experiment_id: EXP-107
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:47:12+08:00
  - status: RUNNING
    at: 2026-09-13T10:47:12+08:00
  - status: INVALID
    at: 2026-09-13T10:50:28+08:00
prior_experiment: EXP-106
hypothesis: With the verified ROS/worktree overlay sourced normally, Coordinator unavailability during exact dynamic execution causes Worker-side independent lease revocation, bounded controller cancel-and-confirm, and fencing of all later goals from that lease.
single_variable: Remove shell nounset from the otherwise identical EXP-106 launch environment and use a new immutable batch/root; product source, install, image, models, config, point and fault sequence remain fixed.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v2-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-107
worker_count: 1
max_points_per_worker: 1
selection: task_start
fault_sequence:
  - wait for exact Worker-owned dynamic consumer and active controller evidence
  - verify and record Coordinator, Worker and consumer identities
  - SIGSTOP exact Coordinator for longer than heartbeat_timeout_s
  - capture controller/joint/TF/MuJoCo/Planning Scene/process state and require consumer/controller stop before Coordinator resume
  - SIGCONT the same Coordinator and require conservative adjudication, no later revoked goal and exact cleanup
success_criteria: All EXP-106 success criteria, with the injection demonstrably inside active execute and cancellation complete before SIGCONT.
failure_criteria: Any missed fault window, identity drift, late cancellation, later revoked goal, uncertain physical classification, incomplete evidence, or residual state.
invalid_criteria: Wrong overlay, pre-existing root, signal to an unverified identity, or an injection before active execute.
provenance:
  source_commit: a9e2b27832a892c70f663895ebff6540b411ef49
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:beae4e2cfdf5e971c8be078b0ee36af1232a414b027e1cd1971f609ea1869681
observed:
  - The corrected shell started Broker g1 and Worker g1, but the selected overlay omitted the worktree mujoco_ros2_control, mujoco_ros2_control_plugins and mujoco_3d_lidar prefixes.
  - The runtime log proves CameraPlugin was absent from the loaded plugin registry. Plugin-loader construction then aborted before SimulationEvidencePlugin initialization, so reset failed closed with initial evidence unavailable.
  - The command exited 1 in 32.717163 s before any dynamic consumer or controller goal. task_start remained UNRUN; cleanup removed the exact Worker/Broker/ROS/container tree and the corrected residual audit is clean.
conclusion: INVALID mixed/incomplete overlay; no heartbeat fault was injected and no physical result is inferred.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-107.log sha256=214d4a07d1677d22d3fb2c34790ce62fc5378ffaf154e3221ef81f25cd40d615
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-107.time sha256=c2ce07815c1548b5d50ef1aeb4ab456257b3bb46d37ad686e647fbea23df988e
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-107/coordinator/aggregate_results.json sha256=b0aa916e7f941815a297356fbb07cda0bd5dd6d17bba4407cb16978e8e96b07f
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-107/workers/worker-01/worker-run-results.json sha256=1b30ecb37b4448727c2ca51e0a653b2e95321ce172e5f72757dfa87887b7358c
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-107-cleanup-audit-r2.json sha256=500e9219a69378aba4930a2806370561f0d49018dab2c390f1eb4b2b8e6fac41
  - post-107-cleanup-audit.json is retained as an invalid self-matching process-filter diagnostic and is not used for cleanup acceptance
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
decision: KEEP_INVALID
next_experiment: EXP-108
```

```yaml
checkpoint_id: CP-094
last_valid_experiment: EXP-105
current_hypothesis: The product fault path remains untested; the locally rebuilt controller, camera/lidar plugin and SO-101 packages must all be explicitly sourced before live runtime admission.
working_tree_status: EXP-107 invalid result is ledger-only; exact cleanup is complete.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Worktree CameraPlugin registry absence, not the reviewed heartbeat implementation, caused EXP-107 to fail closed before execute.
open_risks:
  - Execute heartbeat/lease revocation remains pending under the complete explicit overlay.
next_command: Preregister EXP-108 with a new root and source all worktree controller/plugin and application package prefixes before repeating the fault sequence.
```

## EXP-108 — Execute heartbeat/lease-revocation fault with complete overlay

```yaml
experiment_id: EXP-108
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:50:28+08:00
  - status: RUNNING
    at: 2026-09-13T10:50:28+08:00
  - status: INVALID
    at: 2026-09-13T10:54:31+08:00
prior_experiment: EXP-107
hypothesis: The complete worktree overlay will reach active dynamic execution, after which exact Coordinator suspension will be handled by independent Worker revocation and bounded controller stop before Coordinator resume.
single_variable: Add only the three omitted worktree controller/plugin package prefixes and use a new batch/root; all product inputs and the EXP-107 fault sequence remain fixed.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v3-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-108
worker_count: 1
max_points_per_worker: 1
selection: task_start
overlay_order:
  - /opt/ros/jazzy
  - worktree mujoco_ros2_control_msgs, mujoco_ros2_control, mujoco_ros2_control_plugins, mujoco_3d_lidar
  - worktree so101_mujoco_support, so101_teleop, so101_demo_py
fault_sequence: Identical to EXP-107, including proof of active execute, exact identity checks, stop longer than heartbeat timeout, pre-resume cancel confirmation, resume, conservative adjudication and cleanup.
success_criteria: Identical to EXP-107, plus worktree prefix readback for all eight explicitly sourced packages.
failure_criteria: Identical to EXP-107.
invalid_criteria: Any incomplete/mixed overlay, pre-existing root, unverified signal target, or missed active-execute window.
provenance:
  source_commit: 29fec8a90d3fdbe6c1790ed67c3f3a6e6cba48fa
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:beae4e2cfdf5e971c8be078b0ee36af1232a414b027e1cd1971f609ea1869681
observed:
  - The complete overlay reached dynamic execute and the one-point task_start run physically PASSED in 104.150161 s with a DONE dynamic manifest, generation 2 recovery, qualification true and exact cleanup.
  - The external observer found an active arm goal, but its separate signal command ran after the short final execute window closed. Exact Coordinator identity verification failed closed because the PID no longer existed, and no signal was sent.
conclusion: INVALID fault-orchestration evidence despite a valid normal physical pass; no heartbeat fault occurred and the empty failed-observer files are retained but not authoritative.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-108.log sha256=3d9ecb2fbc1c56146f79f634f697c4d6a6760e284163814311e3860d9b3550f7
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-108.time sha256=7c93275e62f1d924d815e03f4db343c2a0662d48fdee85cf14393be2bc72b5e9
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-108/coordinator/aggregate_results.json sha256=90fc79eea6e798fad01139507ee40a72ce70ad1074b486dce353349aaffa763c
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-108/workers/worker-01/attempts/task_start/task_start-lease-1/sealed/attempt_result_manifest.json sha256=0475d5be9c464c9a588ba770d8ab607149b541e031346f0ca38a430caf0def2d
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-108/workers/worker-01/attempts/task_start/task_start-lease-1/sealed/dynamic/dynamic-execute-manifest.json sha256=385cc4a1ef86af8a6e885000b573357806814da8ce56d5f81150fa0ead730c6e
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-108-cleanup-audit.json sha256=d1d2a80cbcd2090b80dd8396d684a1614d69c0f2d1d690407497bfe0a8232032
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
decision: KEEP_INVALID
next_experiment: EXP-109
```

```yaml
checkpoint_id: CP-095
last_valid_experiment: EXP-105
current_hypothesis: The complete overlay and normal execute path are live-qualified by EXP-108, but the safety finding still requires an observer that signals inside the approximately one-second controller-goal window.
working_tree_status: EXP-108 evidence is ledger-only and cleanup is complete.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Complete explicit overlay reaches and passes physical execute.
  - A sequential human-paced observer is too slow for the active-goal fault window and must be replaced by a local high-rate exact-identity monitor.
open_risks:
  - Heartbeat revocation under active execute remains pending.
next_command: Preregister EXP-109 and run the command plus high-rate exact-identity fault observer in one shell so SIGSTOP occurs while accepted-goal count exceeds terminal-goal count.
```

## EXP-109 — High-rate execute heartbeat/lease-revocation fault

```yaml
experiment_id: EXP-109
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:54:31+08:00
  - status: RUNNING
    at: 2026-09-13T10:54:31+08:00
  - status: INVALID
    at: 2026-09-13T10:58:20+08:00
prior_experiment: EXP-108
hypothesis: A 50 ms local observer bound to the exact Coordinator PID/start-time/cmdline can inject SIGSTOP between controller goal acceptance and terminal status, allowing direct proof that Worker revocation cancels while Coordinator and normal execution remain blocked.
single_variable: Co-locate launch and a 50 ms exact-identity/log-state observer in one shell; overlay, source, image, models, point, N=1/K=1 and fault semantics remain EXP-108-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v4-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-109
worker_count: 1
max_points_per_worker: 1
selection: task_start
injection_predicate:
  - exact dynamic_cup_pick_place process for this root exists
  - command log accepted-goal count is greater than completed/cancelled/aborted controller-goal count
  - Coordinator PID, start-time and cmdline still equal launch identity
success_criteria:
  - SIGSTOP readback reports Coordinator state T during an active goal
  - after more than heartbeat_timeout_s and before SIGCONT, exact dynamic consumer is gone and all action status arrays contain no active goal
  - joint, TF, authoritative MuJoCo physical, Planning Scene, process and fresh visual evidence are captured
  - resumed Coordinator adjudicates conservatively, no later goal for the revoked lease appears, and cleanup is exact
failure_criteria: Signal misses active goal; cancellation requires SIGCONT; any later revoked goal, uncertain physical promotion, stale identity, incomplete evidence or residual state.
invalid_criteria: Incomplete overlay, pre-existing root, observer timeout before predicate, or exact identity mismatch before signal.
provenance:
  source_commit: cd04f7626bd3996aebc610cb4f828317e87a798f
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:beae4e2cfdf5e971c8be078b0ee36af1232a414b027e1cd1971f609ea1869681
observed:
  - The co-located observer made its own long-lived parent shell cmdline contain the dynamic-consumer/root predicates before admission.
  - Resource admission correctly rejected that live candidate as PROC_METADATA_UNVERIFIABLE. The command exited 1 in 0.541116 s before batch-root allocation, and no Broker, Worker, ROS, controller or physical action started.
conclusion: INVALID observer composition; admission safety behavior is correct, but no heartbeat fault was exercised.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-109.log sha256=9e267abe23aee925b1892a82f70a7a082262abe8a575809e72b130229b2376ad
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-109.time sha256=8f778e1d6dc0d6aae63dbb106367b2f324a7da829e6d99d4a58ce050e44c2add
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-missed-109.json sha256=f4cc676dad7ff4d71894cebd3855f1eb9bfde9e25453a3aa7cded0c854a5ac90
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP109.txt sha256=936b50eed5623575fe1b1aa692311e2be606cf7591ff8ad3054bb71285300579
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
decision: KEEP_INVALID
next_experiment: EXP-110
```

```yaml
checkpoint_id: CP-096
last_valid_experiment: EXP-105
current_hypothesis: Admission must complete under a minimal launch parent before a separate observer containing runtime predicates is introduced; the successful EXP-108 timing leaves ample startup time to attach that observer immediately after root creation.
working_tree_status: EXP-109 invalid pre-admission evidence is ledger-only; no product process or root exists.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Resource admission correctly rejects an unverified process whose cmdline appears to collide with the task runtime.
open_risks:
  - Execute heartbeat/lease revocation is still not live-exercised.
next_command: Preregister EXP-110; start the minimal batch parent first, then immediately attach a separate high-rate observer after admission begins.
```

## EXP-110 — Separate high-rate execute heartbeat observer

```yaml
experiment_id: EXP-110
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T10:58:20+08:00
  - status: RUNNING
    at: 2026-09-13T10:58:20+08:00
  - status: VALID
    at: 2026-09-13T11:01:46+08:00
prior_experiment: EXP-109
hypothesis: Starting the verified minimal batch parent before attaching a separate 50 ms observer avoids admission self-collision and still injects exact Coordinator SIGSTOP during an active dynamic controller goal.
single_variable: Move the EXP-109 monitor into a separate process started immediately after the minimal launch process; all product inputs, predicate, signal and evidence criteria remain fixed.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v5-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-110
worker_count: 1
max_points_per_worker: 1
selection: task_start
injection_predicate: Exact dynamic consumer exists, accepted-goal count exceeds reached-goal count, and Coordinator PID/start-time/cmdline match the launch receipt.
success_criteria: Exact Coordinator is stopped in state T during active goal; after heartbeat bound and before SIGCONT the consumer is gone and controller goals are inactive; joint/TF/MuJoCo/Planning Scene/visual/process evidence is complete; resume produces conservative adjudication, no later revoked goal, and exact cleanup.
failure_criteria: Missed active window, late cancellation, later revoked goal, identity mismatch, physical uncertainty without conservative classification, incomplete evidence, or residue.
invalid_criteria: Admission failure, pre-existing root, observer timeout, or signal predicate/identity failure.
provenance:
  source_commit: 89b6198612b7003522386ace4a72b8d87c588203
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:beae4e2cfdf5e971c8be078b0ee36af1232a414b027e1cd1971f609ea1869681
observed:
  - The exact Coordinator was stopped in state T at 10:58:59 while controller accepted-goal count 11 exceeded reached-success count 10 and the exact dynamic consumer identity was live.
  - Before Coordinator resume at 10:59:30, the dynamic consumer still existed and the counts had advanced to accepted 23/reached 22. Thus twelve later goals were accepted after lease heartbeat acknowledgement was unavailable.
  - Controller cancel appeared only at 10:59:28, after the consumer's MOVEIT_EXECUTION_MONITOR_ABORTED receipt. Source inspection identifies the boundary: ParallelWorkerRuntime.cancel_motion synchronously waits for WorkerOwnedProcessTree.stop, whose SIGINT grace is 20 s, before calling the controller cancellation port; the tracked ros2-run wrapper does not immediately stop its actual console descendant.
  - Pre-resume controller status arrays had only terminal status 4 entries, but this was too late for the heartbeat bound. Authoritative MuJoCo state showed the cup displaced and elevated at [-0.07799,-0.24724,0.22811], while Planning Scene still attached plastic_cup to gripper. The attempt was conservatively INDETERMINATE, recovery did not complete, command exited 147, and batch qualification/cleanup flags were false.
  - External RGB-D capture failed because the subsequent authoritative paused snapshot stopped fresh sensor production; the attempt-local initial RGB remains fresh visual evidence, and no false terminal visual was fabricated.
  - Final exact residual audit is clean despite the batch-level failed cleanup gate.
conclusion: VALID_RED; the original F1 unit fix does not meet its live safety bound because consumer retirement serially delays controller cancellation and signals a wrapper rather than the actual consumer. This blocks Broker and qualification work until repaired.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-110.log sha256=4f20793f2d232413fae46269643fc3b479fdcbc456a84d31595aadfe0cf26e14
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-stop-110.readback.json sha256=872ab5339360a4d4712f5a4a54aa0d12cee61d785f061063fa328d90d7f4c3fd
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-cont-110.json sha256=14d67f52dc41282bb2d2a25a7dea885c4a0478d064b9cad4434c1c1b0fabaa03
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/controller-arm-status-110.txt sha256=f0e117e574c2127015690165e87b695c706e541a82ea8f0943cf337a9d7d0667
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/controller-execute-status-110.txt sha256=9dde65afde8fbfee37d1fb5cebc5fa4b8e03c907fc92a65b407f261ad5e5c614
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/joint-state-110.txt sha256=43e23dab9516a056fbf87bab1dfb81617bffb7b7e8a1cdad1649337dce43f8a6
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/mujoco-physical-110.json sha256=49a8b84cba81f6bf5136ab82ebc3958f7ba2eeb857f5be345c902f8217f95377
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/planning-scene-110.txt sha256=1cecc8f04ce65ba3c3a17fb60c0d889528a844810c8880b6c2e89f17e9058f94
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/rgbd-capture-110.json sha256=bf9e27827b3cc80f7c21d84165c78282d612677779a43f6d1111b15718382541
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-110/coordinator/aggregate_results.json sha256=e15d2319db0f13239048947c89f0aad67506335addcff6c70dd5e3df1dfcfd7d
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-110-cleanup-audit.json sha256=eac852a20c5e9c878c3fbddd0d1793c1f33b14e1075156c086a8fffc669ce950
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
decision: FIX_BEFORE_NEXT_LIVE_GATE
next_experiment: EXP-111
```

```yaml
checkpoint_id: CP-097
last_valid_experiment: EXP-110
current_hypothesis: The remaining F1 defect is local to serial child-retirement/controller-cancel order plus wrapper process identity; signalling the actual consumer and starting controller cancellation without waiting for child exit should close the live bound.
working_tree_status: EXP-110 live RED and diagnosis are ledger-only; source is unchanged and residual cleanup is exact.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Live heartbeat loss is conservatively classified, but controller cancellation is delayed beyond five seconds and later goals are not fenced.
open_risks:
  - The minimum fix needs deterministic RED/GREEN, package rebuild/image provenance, then another controlled live fault before any Broker or qualification gate.
next_command: Commit EXP-110/CP-097, preregister EXP-111, add a deterministic blocking-consumer-stop RED and direct-consumer identity contract, then make the smallest local fix.
```

## EXP-111 — Bound consumer stop and controller cancellation concurrently

```yaml
experiment_id: EXP-111
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:01:46+08:00
  - status: RUNNING
    at: 2026-09-13T11:01:46+08:00
  - status: VALID
    at: 2026-09-13T11:06:12+08:00
prior_experiment: EXP-110
hypothesis: Production cancellation misses the heartbeat bound only because the controller cancellation call is serialized after a 20 s wait on a ros2-run wrapper; direct consumer identity plus concurrent consumer interrupt/controller cancellation will cancel before a blocked stop returns and prevent later goals.
prediction: A deterministic test that blocks process stop will show controller cancellation absent before release on current code; after the fix it will observe cancellation while stop is still blocked, exact direct module argv, and no subsequent consumer action opportunity.
single_variable: Change only dynamic consumer process identity and cancellation ordering; do not alter heartbeat, lease, controller APIs, physical evidence classification, recovery policy or Broker gates.
lifecycle: ISOLATED_STACK
success_criteria:
  - deterministic RED fails because controller cancellation waits for blocked consumer stop
  - GREEN proves controller cancellation begins while consumer stop is blocked and the actual consumer is directly signal-addressable
  - existing Worker revocation, runtime process ownership, dynamic execution and adjacent tests pass
failure_criteria: Any stale-generation cancellation, sibling process signal, controller cancellation delay, direct-consumer provenance ambiguity, test regression or weakened conservative classification.
invalid_criteria: Wrong overlay, reused pytest scratch, test collection failure, or a test that only asserts mocks without exercising ParallelWorkerRuntime.
provenance:
  source_commit: 1a023f3a6be3caf04a6af03d68a518ecb320f9e0
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
observed:
  - Deterministic RED failed both intended contracts: controller cancellation was absent while process stop was blocked, and the consumer argv began with ros2 run rather than the directly signal-addressable Python module.
  - The minimum fix starts exact consumer retirement in its own thread, invokes controller cancellation immediately, then joins retirement before reporting completion. It also launches the dynamic CLI directly as sys.executable -m so101_demo.cli.dynamic_cup_pick_place, so the manifest-owned PID is the actual consumer rather than a ros2-run wrapper.
  - Focused GREEN passed 2 tests in 0.11 s. Adjacent ParallelWorkerRuntime, ParallelRosRuntime and ParallelWorker suites passed 183 tests in 3.56 s.
  - Mutation check: serializing _cancel_motion after stop makes the blocking test fail; restoring ros2 run makes the argv contract fail; wrong-lease cancellation remains rejected by unchanged exact lease-key checks.
conclusion: VALID; the live RED boundary is fixed locally with direct consumer identity and concurrent consumer interrupt/controller cancellation, without altering heartbeat, lease, recovery, evidence or Broker policy.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-f1-live-red-111.log sha256=ac274dee707bf8750955d4a9e7c2588df17a17bc89f99b054656b912b8b1a2a8
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-f1-live-green-111.log sha256=b57b02970107870af2f2fe4f1342cd9fefa6624e5e0fdf6496a25980da0b4bbb
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-f1-live-adjacent-111.log sha256=dcd8bb7511bc5b032c4058c350852cee679ad6437d1b6b6ca002a0b84dc4ab87
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f1-live-red-111
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f1-live-green-111
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f1-live-adjacent-111
retention_rule: Retain RED/GREEN/adjacent/package/live evidence and scratch; delete nothing without explicit user authorization.
decision: KEEP
next_experiment: EXP-112
```

```yaml
checkpoint_id: CP-098
last_valid_experiment: EXP-111
current_hypothesis: The local F1 live-bound fix passes focused and adjacent tests; a fresh affected-package build/test and rebuilt image/provenance gate is required before repeating live fault injection.
working_tree_status: Runtime, test and ledger changes form one coherent verified F1 follow-up fix; ignored SDD progress is synchronized separately.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Controller cancellation no longer waits behind slow consumer retirement in the runtime orchestration contract.
  - The exact process manifest now owns the actual dynamic Python module process.
open_risks:
  - Full package/build/image gate and repeated live heartbeat fault remain pending.
next_command: Commit EXP-111/CP-098, then run EXP-112 complete package build/test and immutable image/provenance smoke before any new live action.
```

## EXP-112 — Rebuild/package/image gate for live heartbeat fix

```yaml
experiment_id: EXP-112
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:06:12+08:00
  - status: RUNNING
    at: 2026-09-13T11:06:12+08:00
  - status: VALID
    at: 2026-09-13T11:14:13+08:00
prior_experiment: EXP-111
hypothesis: The direct-consumer/concurrent-cancel fix builds cleanly, preserves the complete ordinary package suite, installs the exact module, and produces a provenance-bound immutable image and dual-model smoke suitable for the next live fault.
single_variable: Replace only the F1 follow-up source from EXP-105; catalog, config, models, build type, image tag and smoke input remain frozen.
lifecycle: ISOLATED_STACK
success_criteria: Fresh four-package symlink build passes; complete ordinary so101_demo_py suite has zero errors/failures/skips; source/install runtime trees and console paths match; rebuilt immutable image and both model smokes pass; cleanup is exact.
failure_criteria: Any build/test/provenance/image/model/cleanup failure or mixed path blocks live fault retry.
invalid_criteria: Reused scratch, tempfile outside registered NVMe scratch, wrong interpreter/overlay, benchmark collection, or dirty provenance.
provenance:
  preregistration_source_commit: 918ddc0985fd70f19a3b9dceb2feeae6e940d8a8
  qualified_source_commit: 147bc0caa26394217bc07827d46439560148f436
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f0d4c07d6a93f563218824452df5765eddeddf3cf6b65252899255159053d406
  broker_source_sha256: b40c5db5dbd97e77c3525294f468605b33930bbffbcc75bdf737a10628f99506
commands:
  - command: fresh four-package colcon build under scratch/p125/tmp
    exit_code: 0
    elapsed_s: 2.35
  - command: complete ordinary so101_demo_py colcon test and scoped test-result under scratch/p126/tmp
    exit_code: 0
    elapsed_s: 86.02
  - command: immutable Broker image build under scratch/p127/tmp
    exit_code: 0
    elapsed_s: 12.35
  - command: p128/p129/p130 smoke admission prechecks
    exit_code: 1
    classification: INVALID_SETUP_ATTEMPTS; no container/model/GPU action
  - command: dual-model immutable-image smoke under scratch/p131/tmp
    exit_code: 0
    elapsed_s: 8.94
  - command: production verify_provenance with full worktree overlay and exact frozen inputs
    exit_code: 0
observed:
  - The fresh four-package symlink build passed. The complete ordinary package suite passed 2839 tests with zero errors, failures or skips and four known warnings; benchmark_test was not collected.
  - Production provenance binds clean commit 147bc0caa26394217bc07827d46439560148f436, worktree libexec/import/module/config/catalog/model paths, equal source/install module-tree hash 74c5b1b1b043115420925e9252c765e6c3139de8aac101de913e551254a39efc, and source/image hash b40c5db5dbd97e77c3525294f468605b33930bbffbcc75bdf737a10628f99506.
  - The rebuilt immutable image is sha256:f0d4c07d6a93f563218824452df5765eddeddf3cf6b65252899255159053d406. YOLO and Grounded-SAM each returned one QUALIFIED candidate on the frozen smoke image.
  - p128, p129 and p130 were rejected before container creation while establishing the required owner-only root/workers/ipc layout: missing root, missing workers directory, then ipc mode 0775. Their logs are retained as invalid setup attempts. p131 used exact mode 0700 and passed.
  - Post-smoke readback found no related process, running container or GPU compute application. The initial user request is also satisfied by committed .codex-task/ ignore rule 147bc0caa26394217bc07827d46439560148f436.
conclusion: VALID; package, install, immutable image, dual-model smoke, production provenance and exact cleanup gates pass for the F1 live retry.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p125-colcon-build.log sha256=165a127092f0b9bad0d82bd48ab9d985e16c449f9cc245257160642f291a07a8
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p126-colcon-test.log sha256=094e6aec62cbd96c84ad7c05c1f641588b3a1adae4fe5114cafe77f76175b94f
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p126-colcon-test-result.log sha256=4b625d83a538e183a2d37077cb94c17199f640f53922904ccaff238841bac644
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p126-colcon-test.provenance sha256=6ea54d9c473c85e2b73dbf58418b140edd4d046dc6827084ac2f51809c4a37e5
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p127-image-build.log sha256=f071c5a5edc3e1301a2b3a67aee7ad99f9d0c148390d6306104685e2a9ff944a
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-image-build-112.json sha256=f023f4e1133907483a0d5fcd042a09fb16f966401e34c6a4f7992571c76b852f
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p128-model-smoke.log sha256=b24a71aed36d4d1f33ae9dbc617999eabe5779143ff3fe99847b30b632bee414
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p129-model-smoke.log sha256=d846854599ffdc7a95a07780e49c270dca04358e0d639c7bf45fcfc063889b48
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p130-model-smoke.log sha256=880b6683a09afe9fe0c3f256675f3e0c9eac0449c668b5f02671ff03ee158c63
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p131-model-smoke.log sha256=d8e9804193886cfe1eef1613f3ba3a74885d6ae2c6c26505b1cb7ec0ce4a36da
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-smoke-admission-112.json sha256=28f47c25e4bc28cb25a3e9ed7d18a0f6351d54344eb403365175ae6113fd1f96
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-remediation-112-smoke/ipc/smoke.json sha256=da0b045d7f761cbca283f89c3a6ef1df267cd6d12f5649c1b01660c4e4b7279e
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-production-provenance-112.json sha256=71c88efeb05b22a44881b8c3815e7844234e2592d8201e3f147b566b49ca8ae5
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-112-cleanup-audit.json sha256=27b575ecbbc39d8172d555b9d364e4d44d5bf7f2df740292d288886de61fea3f
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p125
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p126
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p127
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p128
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p129
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p130
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p131
retention_rule: Retain all build/test/image/smoke evidence and scratch; delete nothing without explicit user authorization.
decision: KEEP
next_experiment: EXP-113
```

```yaml
checkpoint_id: CP-099
last_valid_experiment: EXP-112
current_hypothesis: The rebuilt full overlay and image preserve the F1 cancellation fix; controlled Coordinator suspension during an active goal should now cause direct consumer retirement and controller cancellation within the heartbeat bound, before Coordinator resume.
working_tree_status: EXP-112 result is ledger-only; source and installed runtime are clean and production-provenance bound.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Complete package and immutable dual-model gates pass after the F1 live-bound fix.
  - Production provenance and post-smoke cleanup are exact.
open_risks:
  - The fixed F1 path still requires the same controlled live execute fault and physical/MoveIt/controller readback.
next_command: Commit EXP-112/CP-099, preregister EXP-113 with a fresh batch/root, then repeat the separate exact-identity high-rate heartbeat observer and capture live cancellation before Coordinator resume.
```

## EXP-113 — Post-fix execute heartbeat/lease-revocation fault

```yaml
experiment_id: EXP-113
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:15:32+08:00
  - status: RUNNING
    at: 2026-09-13T11:15:32+08:00
  - status: INVALID
    at: 2026-09-13T11:17:12+08:00
prior_experiment: EXP-112
hypothesis: With direct consumer identity and concurrent controller cancellation, exact Coordinator suspension during an active dynamic controller goal will revoke the lease, stop the consumer and cancel the controller within the heartbeat bound before Coordinator resume.
single_variable: Replace only the F1 runtime/image qualified by EXP-112; preserve the EXP-110 task_start point, N=1/K=1, complete overlay, exact observer predicate, Coordinator SIGSTOP/SIGCONT and evidence criteria.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v6-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-113
worker_count: 1
max_points_per_worker: 1
selection: task_start
injection_predicate:
  - exact direct so101_demo.cli.dynamic_cup_pick_place process for this root exists
  - command-log accepted-goal count exceeds terminal reached/cancelled/aborted count
  - Coordinator PID, start-time and cmdline match the launch receipt
success_criteria:
  - exact Coordinator is stopped in state T during an active goal
  - after more than heartbeat_timeout_s and before SIGCONT, exact dynamic consumer is absent, accepted-goal count does not advance after revocation and all action status arrays contain no active goal
  - fresh RGB-D, joint, TF, authoritative MuJoCo physical, Planning Scene and process evidence are captured before resume
  - resumed Coordinator adjudicates the in-flight attempt conservatively, grants no later revoked goal and completes exact residual cleanup
failure_criteria: Cancellation requires Coordinator resume or exceeds heartbeat bound; any later revoked goal, active controller status, unverifiable identity, unsafe physical promotion, incomplete evidence or residue.
invalid_criteria: Pre-existing root, incomplete overlay, missed active-goal window, observer timeout, identity mismatch or evidence tool failure before the intended fault.
provenance:
  source_commit: cb8cb52778db93fd52f34c62c280ae8700853b28
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f0d4c07d6a93f563218824452df5765eddeddf3cf6b65252899255159053d406
retention_rule: Retain all command, observer, controller, physical, visual, process, result and cleanup evidence; delete nothing without explicit user authorization.
observed:
  - Production resource admission rejected ROS_DOMAIN_IN_USE: 181 in 0.53 s before batch-root creation. No Broker, Worker, MuJoCo, controller, model, GPU or physical action started.
  - Exact process inspection identified PID 2342902 as the orphaned ROS 2 daemon for domain 181 created during EXP-110. ROS_DOMAIN_ID=181 ros2 daemon stop terminated that exact process, and readback found no daemon in the 181-183 pool.
conclusion: INVALID pre-admission environment collision; the safety gate behaved correctly and no F1 evidence was collected.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-113.log sha256=01df72b57542ae9f155f5ae2a4fb6ee64d3c874cd1ee46f07f9275cc66e8c38a
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-113.time sha256=344606806699741bade58b6e97d99ea7f2ae2ad42ee999f7fd068036ec8750b4
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-113.exit sha256=4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/ros-domain-181-cleanup-113.log sha256=1f5c226dd0f1d720f7dec91a8cd7384f52e9cd76cfdeb1fb44286b406b540ab7
decision: KEEP_INVALID
next_experiment: EXP-114
```

```yaml
checkpoint_id: CP-100
last_valid_experiment: EXP-112
current_hypothesis: With the stale domain-181 daemon removed, the unchanged EXP-113 fault sequence can pass production resource admission and exercise the fixed live F1 boundary.
working_tree_status: EXP-113 invalid result and EXP-114 preregistration are ledger-only; source/install/image remain unchanged and clean.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Production admission correctly fails closed on a live ROS daemon and creates no batch root.
  - The exact stale task-owned daemon was stopped through ros2 daemon stop; domain pool 181-183 is now clear.
open_risks:
  - F1 post-fix live cancellation remains unexercised.
next_command: Commit CP-100 and repeat the unchanged live fault as EXP-114 using a fresh batch ID/root.
```

## EXP-114 — Clean-pool post-fix execute heartbeat fault

```yaml
experiment_id: EXP-114
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:17:12+08:00
  - status: RUNNING
    at: 2026-09-13T11:17:12+08:00
  - status: INVALID
    at: 2026-09-13T11:20:40+08:00
prior_experiment: EXP-113
hypothesis: With the 181-183 domain pool clear, the post-fix runtime will enter active execution and independently revoke, stop and cancel the in-flight lease within the heartbeat bound while Coordinator remains stopped.
single_variable: Remove only the verified stale domain-181 daemon; all source, image, point, N=1/K=1, complete overlay, exact observer predicate, signals and evidence criteria remain EXP-113-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v7-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-114
worker_count: 1
max_points_per_worker: 1
selection: task_start
injection_predicate: Exact direct dynamic module exists, accepted-goal count exceeds terminal count, and exact Coordinator PID/start-time/cmdline match.
success_criteria: Exact Coordinator state T during the active goal; after heartbeat bound and before resume the dynamic consumer is absent, no active controller goal or later accepted goal exists, complete fresh visual/numeric/MoveIt/process evidence is captured, resumed adjudication is conservative, and residual cleanup is exact.
failure_criteria: Cancellation requires resume or exceeds bound; later revoked goal, active controller status, unsafe promotion, incomplete evidence or residue.
invalid_criteria: Admission failure, pre-existing root, missed active window, observer timeout, identity mismatch or evidence tool failure before fault.
provenance:
  source_commit: e359599db8c2ee7f089a8c103b18b295fb9d540b
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f0d4c07d6a93f563218824452df5765eddeddf3cf6b65252899255159053d406
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
observed:
  - The clean pool passed production admission and the unchanged task_start batch physically PASSED with qualification_passed=true and batch_cleanup_complete=true in 90.59 s.
  - Coordinator identity was captured, but manual readback before starting the observer consumed the remaining execute window. The observer found the exact Coordinator already exited and correctly wrote injected=false without sending a signal.
conclusion: INVALID fault orchestration due late observer attachment; the normal post-fix physical pass is retained but supplies no heartbeat-fault result.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-114.log sha256=6df10cfa9c09a93e12539fe7ba9eebda47f5b04a17274b36fae9dbd95d8f5f67
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-114.time sha256=3a69d903d57084799b39796db3b8f5455e3e2e7e58cd8f950f3f087f8009f8c0
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-missed-114.json sha256=de553e43d590fcbbdaabcb808545a8335d1231cfa0e4cdc3a2249f6ed0d68d78
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-114/aggregate_results.json sha256=e1c4822d7adce5fba41cfe45fda4b7cca0f0e594d9dc2c554214c697743c5af6
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-114/cleanup-gates.json sha256=f5572b60d545967c045c8188b3cf60289f6baa28d613a84e55a4b4cb0c3aa517
decision: KEEP_INVALID
next_experiment: EXP-115
```

```yaml
checkpoint_id: CP-101
last_valid_experiment: EXP-112
current_hypothesis: Starting the observer automatically as soon as resource_manifest.json appears will preserve the unchanged clean-pool run while eliminating the manual attachment delay.
working_tree_status: EXP-114 invalid fault result and EXP-115 preregistration are ledger-only; source/install/image unchanged.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - The post-fix runtime completes a normal task_start physical qualification and exact cleanup.
  - The EXP-114 observer sent no signal and therefore did not test F1.
open_risks:
  - F1 still requires an automatically attached active-goal observer.
next_command: Commit CP-101, start EXP-115 minimal launch, and attach the exact observer immediately after root creation with no intervening inspection.
```

## EXP-115 — Immediate-observer post-fix execute heartbeat fault

```yaml
experiment_id: EXP-115
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:20:40+08:00
  - status: RUNNING
    at: 2026-09-13T11:20:40+08:00
  - status: VALID
    at: 2026-09-13T11:28:01+08:00
prior_experiment: EXP-114
hypothesis: Immediate automatic attachment after batch-root admission will inject exact Coordinator SIGSTOP during an active goal and prove the post-fix Worker stops the direct consumer and controller before resume.
single_variable: Remove only the manual readback delay between resource_manifest creation and observer start; source, image, point, N=1/K=1, overlay, predicate, signals and evidence criteria remain EXP-114-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v8-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-115
worker_count: 1
max_points_per_worker: 1
selection: task_start
injection_predicate: Manifest-owned direct dynamic module is live; accepted-goal count exceeds terminal count; exact Coordinator PID/start-time/cmdline match.
success_criteria: Coordinator state T during active goal; after heartbeat bound and before resume exact consumer is absent, accepted count is unchanged and controller statuses are terminal; complete fresh evidence, conservative adjudication and exact cleanup.
failure_criteria: Late/absent cancellation, later revoked goal, active controller status, unsafe promotion, incomplete evidence or residue.
invalid_criteria: Admission failure, pre-existing root, missed window, identity mismatch or pre-fault evidence failure.
provenance:
  source_commit: e93fcb05354b9943de7de3690d68bbb8e27454fc
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f0d4c07d6a93f563218824452df5765eddeddf3cf6b65252899255159053d406
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
observed:
  - The observer verified exact Coordinator PID/start-time/cmdline and manifest-owned direct dynamic module identity, then stopped Coordinator in state T during an active goal at accepted/reached 16/15.
  - Eight seconds after SIGSTOP, the exact direct consumer PID was still live. Before SIGCONT, accepted/reached rose to 25/24 and cancellation indicators appeared only after roughly 16 s. The arm status snapshot was terminal by then, but the five-second heartbeat bound had already been violated by nine later accepted goals.
  - Source-backed timing explains the live delay: the watchdog detects missing ACK after five seconds, but _start_revocation synchronously calls broker.cancel_generation before runtime.cancel_motion. Production Broker cancellation first calls the stopped Coordinator's current_broker RPC; its retry-safe proxy makes two five-second attempts before controller cancellation can begin.
  - The result is conservatively INDETERMINATE with TERMINAL_ACK_FAILED and qualification false. Visual inspection shows the initial cup on the table and terminal cup elevated beside the gripper; no safe terminal promotion is possible. Fresh external RGB-D and concurrent numeric capture became unavailable while the runtime entered recovery, so those files are retained as failed/non-authoritative evidence.
  - Batch-level cleanup flag is false, but the exact external residual audit is clean after stopping the task-owned ROS daemon.
conclusion: VALID_RED; direct process identity and local cancel ordering fixed the previous boundary, but serialized Broker fencing still delays motion cancellation beyond the five-second heartbeat safety contract.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-115.log sha256=ab84084c14379244f14b8080ea31bb15cd29c48b34178a08f6ec0eca8fac271f
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-115.time sha256=5d7c91eafe43d3a45b13bcffe0154a489b17c4420e49b7feba7aada20621665c
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-stop-115.readback.json sha256=fd343eabddfb43f859c29f0e8c42aaaf09e97d528c3318dbf44ae2cc61a56f5b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-cont-115.json sha256=c9460ad298e3d92cff5e046f4d16da7266c801af5ba63bdfe315e6717ad33219
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-snapshot-115-coordinator-stopped.txt sha256=c89c6586d7615f15e6970af917961cada536d75d1605221d434dc186d44cdadb
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/controller-arm-status-115.txt sha256=186a37f8cca439f21f9160fdfe9d53e1670b3f3b4a9e7f6baf94beda5fdda655
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/planning-scene-115.txt sha256=506b875b2f1f55967be9882f3a65f94791fbf31ce9506d1313f3b43c11773829
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP115.txt sha256=29aea7c998a3e301023084a63f03b0db8092444a7a5a1472ee50a978fa0e945b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP115.json sha256=1c1b37d868a6e6490dc931ab5fa436da39be995b54fa4901b1dbf542b6c1bc9f
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-115-cleanup-audit.json sha256=5f0c99fd474390ef79fe36e57f1213050966b964bb0effa2f77f3f73fcf95d60
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-115/aggregate_results.json sha256=b9b39e40be24b7dd3ee85ec68a42e36150acee730798fd6761a98892f1e4f6c5
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-115/workers/worker-01/worker-run-results.json sha256=7cc3f15bc08c874532e99be3805d3d1e82e865cd2a1ea045cf17e026e64ba2f4
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-115/workers/worker-01/attempts/task_start/task_start-lease-1/sealed/initial-rgb.png sha256=5415400052e363f19e321b5f5746913b4d7e8715c8cdb7153def70a91e38a17b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-115/workers/worker-01/attempts/task_start/task_start-lease-1/sealed/terminal-rgb.png sha256=26ef42a5b1d7b2d2e17f94fb292fe30028678377a4e448d9cbd1f70ef0ea934e
decision: FIX_BEFORE_NEXT_LIVE_GATE
next_experiment: EXP-116
```

```yaml
checkpoint_id: CP-102
last_valid_experiment: EXP-115
current_hypothesis: The remaining F1 delay is caused by serial Broker-generation fencing before motion cancellation; starting the two independent safety actions concurrently will preserve the Broker fence while allowing controller stop immediately after watchdog expiry.
working_tree_status: EXP-115 live RED and diagnosis are ledger-only; source is unchanged and external cleanup is exact.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - The direct consumer is now signal-addressable, but Broker cancellation's Coordinator discovery retry adds ten seconds ahead of that signal.
  - No Broker safety gate may be removed or weakened; only independent cancellation scheduling is in scope.
open_risks:
  - Concurrent safety actions need a deterministic blocking-Broker RED/GREEN plus adjacent regression and another full provenance/live retry.
next_command: Commit EXP-115/CP-102, add a deterministic RED where Broker cancellation blocks while runtime cancellation must start, then implement the minimum concurrency fix.
```

## EXP-116 — Run Broker fence and motion cancellation concurrently

```yaml
experiment_id: EXP-116
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:28:01+08:00
  - status: RUNNING
    at: 2026-09-13T11:28:01+08:00
  - status: VALID
    at: 2026-09-13T11:31:33+08:00
prior_experiment: EXP-115
hypothesis: _start_revocation serializes a potentially two-retry Coordinator discovery inside broker.cancel_generation ahead of runtime.cancel_motion; concurrent exact-generation Broker fencing and exact-lease motion cancellation removes that delay without changing either gate.
prediction: Current code fails a deterministic test because runtime.cancel_motion is absent while broker.cancel_generation is blocked; the minimum fix makes it observable before Broker release, then waits for both and preserves exact confirmation/results.
single_variable: Change only _start_revocation scheduling so Broker fence and motion cancellation execute concurrently; keep exact lease keys, generation-bound cancellation, result fields and controller confirmation unchanged.
lifecycle: ISOLATED_STACK
success_criteria: Valid RED at the production ParallelWorker boundary; GREEN proves motion cancellation begins while Broker cancellation remains blocked, Broker fence is still called once for the exact generation, stale lease rejection is unchanged, and adjacent Worker/runtime tests pass.
failure_criteria: Broker gate bypass, missing exact-generation cancellation, controller confirmation before stop completion, duplicate revocation, stale-lease action or regression.
invalid_criteria: Reused pytest scratch, wrong interpreter/overlay, mock-only test outside ParallelWorker, or mutation that does not fail the new assertion.
provenance:
  source_commit: b1fde1f258059606a50021a547e9752099a2e3af
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
retention_rule: Retain RED/GREEN/adjacent/package/live evidence and scratch; delete nothing without explicit user authorization.
observed:
  - Deterministic RED blocked exact-generation Broker cancellation and failed because exact-lease motion cancellation did not start within 200 ms.
  - The minimum fix starts the unchanged Broker cancellation in its own daemon thread, performs unchanged runtime.cancel_motion immediately in the revocation thread, preserves controller confirmation, joins the Broker fence before publishing the revocation completion event, and retains the exact lease-key idempotency map.
  - Focused GREEN passed in 0.03 s. The complete Worker, WorkerRuntime and RosRuntime adjacent set passed 184 tests in 3.51 s.
  - Mutation evidence is the retained RED: serializing Broker cancellation ahead of motion cancellation fails the new contract. Exact-generation Broker invocation remains asserted exactly once, so the safety gate is not bypassed.
conclusion: VALID; the second live F1 delay is fixed locally without weakening Broker fencing or controller confirmation.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-f1-broker-fence-red-116.log sha256=3e5bf0c447b0ceb1b989cf2eb4d677aa6deb5c4170a532c6d050185164c8190b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-f1-broker-fence-green-116.log sha256=ae12dae9ffe6af9dfeed71e5e8ead6b69daab68da54f48e44a2f67e6b48a0eed
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/pytest-f1-broker-fence-adjacent-116.log sha256=47628e2923fcb098e253faad98f812f18c8d618bf66f5d2e689df6bca611bf6f
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f1-broker-fence-red-116
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f1-broker-fence-green-116
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/f1-broker-fence-adjacent-116
decision: KEEP
next_experiment: EXP-117
```

```yaml
checkpoint_id: CP-103
last_valid_experiment: EXP-116
current_hypothesis: Concurrent Broker fencing and motion cancellation pass focused and adjacent contracts; a fresh package build/test plus image/provenance gate is required before another live fault.
working_tree_status: Worker source, deterministic test and EXP-116 ledger result form one coherent uncommitted change.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Motion cancellation no longer waits for a Coordinator-dependent Broker discovery RPC.
  - Broker cancellation remains exact-generation, mandatory and joined before revocation completion.
open_risks:
  - Complete package/image gates and live F1 retry remain pending.
next_command: Commit EXP-116/CP-103, then run EXP-117 full build/test, immutable image, dual-model smoke and production provenance before the next live retry.
```

## EXP-117 — Rebuild/package/image gate for concurrent revocation

```yaml
experiment_id: EXP-117
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:31:33+08:00
  - status: RUNNING
    at: 2026-09-13T11:31:33+08:00
  - status: VALID
    at: 2026-09-13T11:37:20+08:00
prior_experiment: EXP-116
hypothesis: The concurrent revocation fix builds cleanly, preserves the full ordinary package suite, installs exact bytes and produces a source-bound immutable image whose two frozen models smoke successfully.
single_variable: Replace only the F1 revocation scheduling source from EXP-112; frozen catalog, config, models, image tag and smoke input remain fixed.
lifecycle: ISOLATED_STACK
success_criteria: Fresh four-package build; 0-error/failure/skip complete ordinary suite; exact source/install/runtime/image provenance; both model smokes QUALIFIED; exact cleanup.
failure_criteria: Any build/test/provenance/image/model/cleanup failure or mixed path blocks live retry.
invalid_criteria: Reused scratch, tempfile outside registered NVMe root, wrong interpreter/overlay, benchmark collection or dirty provenance.
provenance:
  preregistration_source_commit: a6282d7234d9bb9e75c075555c1bd746834516e7
  qualified_source_commit: 902f373c239ee7ba1447806791ae5f077bdefcb1
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f06ef37ea0c48036cc657e139371783da72d5e1173ee1e182ed3287c21a0e867
  broker_source_sha256: 1b49da7f93167923398d52611e06f01f25bfb140f238be4829183bfbe75f4ef2
commands:
  - command: fresh four-package colcon build under scratch/p133/tmp
    exit_code: 0
    elapsed_s: 2.38
  - command: complete ordinary so101_demo_py colcon test under scratch/p134/tmp
    exit_code: 0
    elapsed_s: 87.11
  - command: p134 test-result invocation containing an accidental extra token
    exit_code: 2
    classification: INVALID_WRAPPER_ONLY
  - command: corrected scoped colcon test-result p134b
    exit_code: 0
  - command: immutable Broker image build under scratch/p135/tmp
    exit_code: 0
    elapsed_s: 13.32
  - command: dual-model smoke under scratch/p136/tmp
    exit_code: 0
    elapsed_s: 9.61
  - command: production verify_provenance with exact frozen inputs
    exit_code: 0
observed:
  - Fresh build passed four packages. The complete ordinary suite collected and passed 2840 tests with zero errors, failures or skips and four known warnings; benchmark_test was not collected. Corrected scoped result readback reports 2840/0/0/0.
  - The first test-result-only wrapper included one accidental non-option token and was rejected without running or altering tests; p134b is the authoritative result readback.
  - Immutable image sha256:f06ef37ea0c48036cc657e139371783da72d5e1173ee1e182ed3287c21a0e867 binds source hash 1b49da7f93167923398d52611e06f01f25bfb140f238be4829183bfbe75f4ef2. The build command succeeded; its auxiliary exit file contains the harmless wrapper text `0 staff`, so image receipt, Docker inspect/provenance and command session are authoritative rather than that malformed helper file.
  - Both YOLO and Grounded-SAM returned QUALIFIED. Production provenance binds clean commit 902f373c239ee7ba1447806791ae5f077bdefcb1, exact worktree module/console/config/model paths, equal source/install module tree hash 840a67bf9f932728d76289b377746de7bd88cf610dc7140171dfbe82bb36e09c, and the same image source hash.
  - Post-smoke audit found no related process, running container or GPU compute application.
conclusion: VALID; the concurrent revocation source is package-, install-, image-, model- and cleanup-qualified for live F1 retry.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p133-colcon-build.log sha256=25c671a8df2573639edbfc787bda650b89e55c0145e1109c8c01dcca5f0ba831
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p134-colcon-test.log sha256=1ed8c282235771e28527bcef1b8837d9d6766e7c577446d2ddb9077475f87efb
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p134b-colcon-test-result.log sha256=028c9fa6f6a1d1dd8c4042b6b23381d1a75a4280cf244c9131ff21bc1d13ca3c
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p135-image-build.log sha256=3d329273e7e63eb8ea782b72367060cd68200bc04808ff95d83b41ecaba95b20
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-image-build-117.json sha256=00fc6f90ab38f929b69089bc91384f9172f4ce43c2479276ee61bf732c7844b5
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/p136-model-smoke.log sha256=f5925fb7a3bef1d967c35a96d6db3aed8ad6d90d7f0f92477f8f158fe17d23a2
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-smoke-admission-117.json sha256=752c1ad99e0e15563ffea8ece50a0d98fbdc13301112325c1e357cb14dedca7b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-remediation-117-smoke/ipc/smoke.json sha256=e303678d72cefe21f95b2d88ad01ceb54b2f5124cb4a9e80b649fcc7b2e87628
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/remediation-production-provenance-117.json sha256=0c6545e52fc7b18c80e397ad7c4b76233397d6d76c34ca9bc0c641a8cae75698
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-117-cleanup-audit.json sha256=27b575ecbbc39d8172d555b9d364e4d44d5bf7f2df740292d288886de61fea3f
deletion_candidates:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p133
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p134
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p135
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p136
retention_rule: Retain all evidence and scratch; delete nothing without explicit user authorization.
decision: KEEP
next_experiment: EXP-118
```

```yaml
checkpoint_id: CP-104
last_valid_experiment: EXP-117
current_hypothesis: The fully rebuilt concurrent-revocation runtime should cancel the direct consumer/controller near heartbeat expiry even though Coordinator-dependent Broker fencing remains blocked until resume.
working_tree_status: EXP-117 result and EXP-118 preregistration are ledger-only; source/install/image are clean and provenance-bound.
owned_processes: NONE
preserved_processes: NONE beyond the active coding session.
confirmed_conclusions:
  - Complete 2840-test and immutable dual-model gates pass after the second F1 repair.
  - Broker fencing remains mandatory while no longer serializing controller cancellation.
open_risks:
  - The post-fix live heartbeat timing, physical/MoveIt consistency and cleanup require repeat evidence.
next_command: Commit CP-104, then run EXP-118 with immediate observer and the rebuilt immutable image.
```

## EXP-118 — Concurrent-revocation live heartbeat fault

```yaml
experiment_id: EXP-118
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:37:20+08:00
  - status: RUNNING
    at: 2026-09-13T11:37:20+08:00
  - status: VALID
    at: 2026-09-13T11:45:00+08:00
prior_experiment: EXP-117
hypothesis: Exact Coordinator suspension during an active goal now triggers direct consumer/controller cancellation after the five-second heartbeat timeout without waiting for the blocked exact-generation Broker fence.
single_variable: Replace only the EXP-115 runtime/image with EXP-117-qualified concurrent revocation; preserve task_start, N=1/K=1, overlay, immediate observer, exact signals and evidence order.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-heartbeat-fault-20260913-v9-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-118
worker_count: 1
max_points_per_worker: 1
selection: task_start
injection_predicate: Manifest-owned direct dynamic module is live, accepted-goal count exceeds terminal count, and exact Coordinator identity matches.
success_criteria: Coordinator state T during active goal; after eight seconds the exact direct consumer is absent, accepted count has not advanced beyond at most the in-flight goal and controller statuses are terminal; complete fresh visual/numeric/MoveIt/process evidence; resumed conservative adjudication; exact cleanup.
failure_criteria: Cancellation exceeds heartbeat bound, later revoked goals, active controller status, Broker fence bypass, unsafe promotion, incomplete evidence or residue.
invalid_criteria: Admission failure, pre-existing root, missed window, identity mismatch or pre-fault evidence failure.
provenance:
  source_commit: 902f373c239ee7ba1447806791ae5f077bdefcb1
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f06ef37ea0c48036cc657e139371783da72d5e1173ee1e182ed3287c21a0e867
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
observed:
  - The observer verified exact Coordinator PID 2388353, start-time and cmdline plus manifest-owned direct consumer PID 2389266, then sent SIGSTOP during an active controller goal at accepted/reached 18/17; exact Coordinator state read back T.
  - The direct consumer was absent at both the six- and eight-second observations. Accepted/reached was 21/21 at six seconds and remained exactly 21/21 at eight seconds, proving no controller goal was submitted after watchdog expiry. The three goals completed between injection and the five-second heartbeat deadline are pre-revocation work; Broker fencing remained blocked on the intentionally stopped Coordinator and completed only after SIGCONT.
  - The controller's durable log contains exactly 21 accepted goals and 21 successful terminal goals, with no active or unmatched goal. The resumed Coordinator preserved the interrupted attempt as INDETERMINATE with TERMINAL_ACK_FAILED; qualification stayed false and no physical result was promoted.
  - Fresh initial RGB inspection shows the cup on the table in an uncorrupted scene. The attempt-bound initial depth, TF and authoritative MuJoCo physical receipt agree on the fresh reset/session and cup-on-table state. The concurrent external RGB-D, TF, Planning Scene and MuJoCo queries raced the fast runtime teardown and are retained as explicit failed/non-authoritative captures; they are not used for terminal promotion.
  - cleanup_gates_passed=true with process, controller and container cleanup successful. batch_cleanup_complete=false solely because Coordinator completion was intentionally interrupted; exact post-run readback found no task process, running container, GPU compute process or ROS daemon in domains 181-183. Unrelated stopped containers were preserved.
  - The launch wrapper first evaluated one harmless malformed LOG assignment containing an extra path token, then assigned the correct command log and ran the batch. The authoritative command receipt is exit 1 in 110.64 s, which is expected for the conservatively INDETERMINATE injected batch.
conclusion: VALID_GREEN; the live five-second heartbeat boundary no longer waits for Coordinator-dependent Broker fencing. Motion stops independently, there is no post-revocation goal, and conservative result/cleanup semantics are preserved.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-118.log sha256=21a2066e9bf059e1a45bda336a135a95c4075aa4b742f20ad0b6613b2f48f4a0
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-118.time sha256=c323e647aca071f46f352f97a8fe6ca1aebd33b5a7cc51688e8f9af77cdc4402
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-118.exit sha256=4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-stop-118.readback.json sha256=aacb0650ef512d071253b6bd42bf14c03bc462dcf31cd06219d02080a50c6cf1
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/fault-heartbeat-cont-118.json sha256=5a83a93a447ac7366c52fa3337914699b54ae70ae9cbbb6dc3fd2714b022f3aa
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-snapshot-118-coordinator-stopped.txt sha256=c0e6b5f340057487932bc52186d5dec7fdf52bd3b194f11bcd6458642ba91e20
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/rgbd-capture-118.json sha256=3d321ec7483c420805b7d7792f16f31e52a0ed6f3b4f032ff770139dc3be7841
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP118.txt sha256=b58fac3d796945cdc48644f3a9e60176cb3e6627fa66929970a39701c48b881b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/visual-inspection-EXP118.json sha256=37d606ea1d01b79bb7ce4bba21478f53d736472a12444d7e4f205fab46a8f280
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-118-cleanup-audit.json sha256=4f45b9216a4ebe76421226b2f3b4b94aa33c7bf36c2e4c890de89cb675b1c343
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-118/aggregate_results.json sha256=b9b39e40be24b7dd3ee85ec68a42e36150acee730798fd6761a98892f1e4f6c5
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-118/cleanup-gates.json sha256=b0eae316bab755537e868c76e0fdd8ebc775412b9bd28cf72268a8dab09bf011
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-118/workers/worker-01/worker-run-results.json sha256=7cc3f15bc08c874532e99be3805d3d1e82e865cd2a1ea045cf17e026e64ba2f4
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-118/workers/worker-01/attempts/task_start/task_start-lease-1/working/initial-rgb.png sha256=5a772f4ffcd9d4880ae8bb9c49b7df42edee29f9691f69f7bdf083e1fba2dce7
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-heartbeat-remediation-118/workers/worker-01/ros-home/log/ros2_control_node_2388778_1789270776603.log sha256=5739cd93d1b84498741ee119c0bc0193955abce91c70c7cc19660b5796431fba
decision: KEEP
next_experiment: EXP-119
```

```yaml
checkpoint_id: CP-105
last_valid_experiment: EXP-118
current_hypothesis: The authenticated health-down path will pause grants and replace an exact still-live but unresponsive Broker generation without consuming Worker K, after which ready/model-loaded generation 2 will be readmitted and remaining work will continue.
working_tree_status: EXP-118 result and EXP-119 preregistration are ledger-only; source/install/image remain the EXP-117-qualified clean candidate.
owned_processes: NONE
preserved_processes: Existing unrelated stopped containers only; no task process or running container remains.
confirmed_conclusions:
  - F1 now has deterministic RED/GREEN, complete package/image provenance and a live execute-mode GREEN at the heartbeat boundary.
  - Broker exact-generation fencing remained mandatory and completed after Coordinator resume; the concurrency change did not bypass it.
open_risks:
  - F2 still needs a live-serving Broker that becomes unhealthy without exiting, followed by exact generation replacement/readmission and no-K-debit evidence.
next_command: Commit CP-105, then run preregistered EXP-119 using an exact identity-verified generation-1 Broker container pause during an in-flight inference request.
```

## EXP-119 — Alive-but-unhealthy Broker execute fault

```yaml
experiment_id: EXP-119
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:45:00+08:00
  - status: RUNNING
    at: 2026-09-13T11:45:00+08:00
  - status: INVALID
    at: 2026-09-13T11:50:00+08:00
prior_experiment: EXP-118
hypothesis: Pausing the exact generation-1 Broker container after it is live-serving and has accepted an inference request will yield a generation-bound health-down outcome while the process remains alive, pause new leases, retire only generation 1, readmit a model-loaded generation 2 and continue eligible work without charging Worker K for the infrastructure fault.
single_variable: Inject only Docker pause into the exact verified generation-1 Broker container during an accepted live inference; source, immutable image, complete overlay, models, execute semantics and frozen runtime limits remain EXP-117-identical.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: parallel-broker-unhealthy-20260913-v1-remediation
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-broker-unhealthy-remediation-119
worker_count: 2
max_points_per_worker: 2
selection: task_start,cup_test_forward_5cm
injection_predicate: Exact generation-1 container ID, immutable image ID, batch/generation labels and /runtime mount match; ready.json and model-loaded receipts validate; at least one authenticated request is present for generation 1; the container process is running before Docker pause.
success_criteria:
  - Generation 1 remains present/alive but unresponsive at injection, an authenticated exact-generation INFRA_ERROR/QUEUE_TIMEOUT/INFERENCE_TIMEOUT event marks Coordinator broker_healthy=false, and no fresh lease is granted during that interval.
  - Supervision retires only exact generation 1, creates generation 2 with new credentials/socket/runtime root, verifies ready plus both model-loaded receipts, and marks healthy only after readmission.
  - The infrastructure-fault attempt does not consume an additional Worker K slot; stale-generation and forged health events remain rejected by the already-qualified production boundary; remaining eligible points continue exactly once.
  - Execute results remain conservative, controller/joint/TF/MuJoCo/Planning Scene/visual evidence is internally consistent, cleanup is exact, and no unrelated process/container is changed.
failure_criteria: Lease grant while unhealthy, wrong-generation retirement, health restored before ready/model-loaded verification, K debit for the infrastructure fault, duplicate point, unsafe physical promotion, residue or unrelated mutation.
invalid_criteria: Pre-existing root, incomplete overlay, missed in-flight request, identity mismatch, Docker pause after Broker already exited, observer/tool failure before injection or admission failure.
provenance:
  source_commit: 902f373c239ee7ba1447806791ae5f077bdefcb1
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f06ef37ea0c48036cc657e139371783da72d5e1173ee1e182ed3287c21a0e867
retention_rule: Retain all command, observer, journal, Broker-generation, model, Worker, physical, visual and cleanup evidence; delete nothing without explicit user authorization.
observed:
  - Production admission rejected the preregistered root before creating it because its Worker socket path exceeded the Unix-domain path bound.
  - Exit 1 occurred in 0.11 s with UNIX_SOCKET_PATH_TOO_LONG. No Broker, Worker, ROS, MuJoCo, controller, container, GPU or physical action started; domains 181-183 remained clear.
conclusion: INVALID_PRE_ADMISSION naming error; shorten only the batch and evidence-root names and repeat the unchanged fault design.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-119.log sha256=ebb4040e9b7a601b2c346bdb5f6a47cc29cfe8c8dffcc40a4d2d2f4f7fd6e262
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-119.time sha256=be4076be4bb20af3e69b733b1bb06e3066802b4c44d9296cc5c9bd4d5d4cead7
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-119.exit sha256=4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
decision: KEEP_INVALID
next_experiment: EXP-120
```

```yaml
checkpoint_id: CP-106
last_valid_experiment: EXP-118
current_hypothesis: EXP-119 was rejected solely by the Unix socket path-length gate; the unchanged F2 injection can reach production with a short registered root and batch ID.
working_tree_status: EXP-119 invalid result and EXP-120 preregistration are ledger-only; source/install/image remain clean and unchanged.
owned_processes: NONE
preserved_processes: Existing unrelated stopped containers only.
confirmed_conclusions:
  - Production path validation failed closed before root creation or any side effect.
open_risks:
  - F2 remains unexercised live.
next_command: Commit CP-106 and launch EXP-120 with only the short root f2-120 and batch ID f2-120 changed.
```

## EXP-120 — Short-root alive-but-unhealthy Broker execute fault

```yaml
experiment_id: EXP-120
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-13T11:50:00+08:00
  - status: RUNNING
    at: 2026-09-13T11:50:00+08:00
  - status: INVALID
    at: 2026-09-13T11:54:00+08:00
prior_experiment: EXP-119
hypothesis: With only the root and batch ID shortened, the EXP-119 exact generation-1 container pause will reach a live in-flight inference, yield authenticated health-down after resume, pause grants, replace/readmit generation 2 and continue without infrastructure K debit.
single_variable: Shorten only evidence_root and batch_id to satisfy the pre-admission Unix socket bound; all EXP-119 source, image, overlay, models, points, N=2/K=2, injection and success criteria remain unchanged.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: f2-120
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/f2-120
worker_count: 2
max_points_per_worker: 2
selection: task_start,cup_test_forward_5cm
injection_predicate: Exact generation-1 container ID, immutable image, batch/generation labels and /runtime mount match; ready/model-loaded receipts validate; a generation-1 Broker input exists; container is running and not paused.
success_criteria: Same as EXP-119: live non-exit health-down, no lease while unhealthy, exact generation-1 retirement, generation-2 ready/model-loaded readmission, no infrastructure K debit, unique continuation, conservative physical evidence and exact cleanup.
failure_criteria: Same as EXP-119.
invalid_criteria: Pre-existing root, incomplete overlay, missed in-flight request, identity mismatch, container already exited, observer/tool failure before injection or admission failure.
provenance:
  source_commit: 902f373c239ee7ba1447806791ae5f077bdefcb1
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f06ef37ea0c48036cc657e139371783da72d5e1173ee1e182ed3287c21a0e867
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
observed:
  - Generation-1 identity, image, labels, runtime mount and both ready/model receipts matched. The observer detected worker-01's input file and paused the exact container for approximately 23 seconds while Docker continuously reported Running=true and Paused=true, then resumed the same PID/container.
  - The file-existence predicate was too late for sub-second YOLO inference: both points had already received generation-1 responses. No health-down or Broker generation 2 occurred; both points normally PASSED, K remained 1 per Worker and exact cleanup passed in 102.48 s.
  - The normal 2/2 physical pass is retained, but it does not exercise F2 and cannot qualify that gate. Exact post-run inspection found no task process, container, GPU process or domain-181/182/183 daemon.
conclusion: INVALID_MISSED_INFERENCE_WINDOW; pause the ready live Broker before requests arrive, allow queued requests to exceed their frozen deadline, then resume the same live process so its production scheduler emits the health-losing outcome.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-120.log sha256=ffca2d4057973f820f6c9043240ad9c5367083f7286e8ff7d4c3049e94cb2e6f
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-120.time sha256=e4995d0b66366299a19d56f78ecac0827668fb837824368c5d60962630a03b25
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/command-120.exit sha256=9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/broker-fault-observer-120.log sha256=0019d220fa8df5975f48bfd6382be42d94ade90a5faa4aa2024f48aca06cbfe3
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP120.txt sha256=d7e22b77c6893e8240ec80426154b8574e91f8f49199af281224a3f457145b0b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/f2-120/aggregate_results.json sha256=9e536567518dd9e0129799dc5cf6af90fe285c3f393e721081d7feab6d89908b
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/f2-120/coordinator/aggregate_results.json sha256=a03954746cf300fe5279e35ffeab54b9e3ebd6fa0af7269178b5c93cdfd7cb2d
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/f2-120/cleanup-gates.json sha256=6f83029001a280b597e0da520f75db1c92e27f15c0de3b81a93ca637a842411e
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/f2-120/workers/worker-01/worker-run-results.json sha256=c13e24d37ad5e00527728690bb0e25eeec520df378727e8b4af704173547f103
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/f2-120/workers/worker-02/worker-run-results.json sha256=fd6f9888ad61ab40fc679fe3ee482d12efeee9f9352a2555e1f23297fc3886f0
decision: KEEP_INVALID
next_experiment: EXP-121
```

```yaml
checkpoint_id: CP-107
last_valid_experiment: EXP-118
current_hypothesis: A pre-request pause after generation-1 is fully ready will cause authenticated requests to wait past queue_deadline_s; resuming that same live process will let the production Broker publish QUEUE_TIMEOUT and health-down before supervision replaces it.
working_tree_status: EXP-120 invalid result and EXP-121 preregistration are ledger-only; source/install/image unchanged and clean.
owned_processes: NONE
preserved_processes: Existing unrelated stopped containers only.
confirmed_conclusions:
  - File appearance cannot serve as an in-flight predicate for the sub-second YOLO path.
  - Docker pause/unpause preserved exact container identity and normal execution/cleanup recovered cleanly when no health event occurred.
open_risks:
  - The queued-request deadline path must produce the authenticated health event before the live F2 gate can pass.
next_command: Commit CP-107 and run EXP-121, pausing exact generation 1 immediately after ready/model-loaded readback and before Worker request arrival.
```

## EXP-121 — Pre-request live Broker queue-timeout fault

```yaml
experiment_id: EXP-121
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-13T11:54:00+08:00
  - status: RUNNING
    at: 2026-09-13T11:54:00+08:00
prior_experiment: EXP-120
hypothesis: Pausing fully admitted generation 1 before its first request, observing both immutable Broker input files while it remains alive/paused beyond the 10-second queue deadline, and resuming the same process will yield authenticated QUEUE_TIMEOUT health-down, lease pause, exact generation replacement and no infrastructure K debit.
single_variable: Move the unchanged exact-container pause earlier, from post-input observation to immediately after generation-1 ready/model-loaded verification; source, image, overlay, config, points, N=2/K=2 and recovery criteria are unchanged.
mode: execute; simulation only
lifecycle: ISOLATED_STACK
batch_id: f2-121
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/f2-121
worker_count: 2
max_points_per_worker: 2
selection: task_start,cup_test_forward_5cm
injection_predicate: Exact generation-1 container is running, unpaused, identity-bound to the immutable image/batch/generation/runtime mount, both ready/model receipts validate, and no Broker input exists yet.
success_criteria:
  - While generation 1 remains Running=true/Paused=true, both Workers create exact attempt-bound Broker inputs and wait past the frozen 10-second queue deadline; generation 1 is then unpaused without exiting.
  - Generation 1 emits authenticated QUEUE_TIMEOUT/INFERENCE_TIMEOUT/INFRA_ERROR, Coordinator marks broker_healthy=false before new lease issuance, supervision retires exact generation 1, and generation 2 receives new credentials/socket plus ready and both model-loaded readmission.
  - Infrastructure failure adds no Worker K debit, no point duplicates, remaining eligible work continues conservatively, and exact process/controller/container/domain cleanup passes.
failure_criteria: No authenticated health event, lease issuance while unhealthy, wrong generation retirement, premature health restoration, K debit, duplicate, unsafe promotion, residue or unrelated mutation.
invalid_criteria: Pre-existing root, admission failure, any Broker input before pause, identity/tool failure before injection or generation 1 exits before unpause.
provenance:
  source_commit: 902f373c239ee7ba1447806791ae5f077bdefcb1
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  broker_image_id: sha256:f06ef37ea0c48036cc657e139371783da72d5e1173ee1e182ed3287c21a0e867
retention_rule: Retain all evidence; delete nothing without explicit user authorization.
decision: RUN
next_experiment: EXP-121
```
