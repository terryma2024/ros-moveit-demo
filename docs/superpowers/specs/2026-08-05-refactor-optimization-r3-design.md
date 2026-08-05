# Refactor Optimization R3 Design

**Date:** 2026-08-05
**Status:** Proposed; implementation requires user approval
**Reviewed baseline:** `origin/main=82d1c5127453f8cba401bf999ca47ccf193b41e2`, `merge-base=60bb4bf2ebb7006ba7f999ab3aaa19103900c218`, R2 `HEAD=20f75267313b5ca7c121fff69dedbd181599efa2`
**Scope:** `pick_place_common`, `so101_gazebo_demo`, `panda_gazebo_demo`, their launch/docs/tests, and installed entry points

## 1. R2 completion evidence

R2 is accepted before this review begins.

- Build completed from `/data/work/ws_moveit/.worktrees/refactor-optimization-r2/install`.
- The final three-package test result is 1,152 tests, 0 errors, 0 failures, 92 skipped.
- A fresh isolated SO-101 run used `ROS_DOMAIN_ID=142` and `GZ_PARTITION=r2-independent-evidence`.
- The injected failure remained `TCP_ENDPOINT_OUTSIDE_TOLERANCE`; execute-resume produced `RECOVER_RETREAT -> ERROR` and preserved the original failure.
- Checkpoint bytes and SHA-256, normalized controller state, normalized `base -> so101_tcp`, joint state, Gazebo object pose/attachment, and MoveIt world/attached membership were unchanged across resume.
- The inspected fresh Gazebo image shows the arm at safe home, gripper open, and the cup upright and detached on the support.
- The isolated stack was cleaned, the worktree remained clean, and neither merge, push, nor `codex-cua` was used.

Authoritative R2 evidence is under `/tmp/so101-r2-independent-20260805-134330-BlFHhA/` on AI-STATION-001.

## 2. Verified review findings

### P1: SO-101 bypasses the physical-grasp validation chain

**Fact**

- `src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp:18-23` declares `MICRO_LIFT`, `WAIT_MICRO_LIFT_STABLE`, and `VERIFY_PHYSICAL_GRASP`, but the success edge from `WAIT_GRASP_STABLE` goes directly to `ATTACH_GAZEBO`.
- `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp:805-835` registers live executors and contracts for all three skipped states.
- `src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp:22-43` locks the bypass into the expected dry-run trace.
- A fresh R2 dry run produced `... CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> ATTACH_GAZEBO ...`; none of the three validation states ran.
- `docs/superpowers/specs/2026-07-30-so101-teleop-web-ui-design.md:243-265` requires `WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_GAZEBO` and says Attach must not replace physical validation.
- `docs/pick-place-launch-parameters.md:28` claims deep SO-101 plan-only runs execute grasp-stability predecessors, which is false for the current implementation.

**Impact**

SO-101 can create Gazebo and MoveIt attachments without first proving that the cup followed the physical micro-lift. This is a simulation safety-contract regression and makes the launch manual materially inaccurate.

**Trigger**

Every successful SO-101 execute or deep plan-only run that passes `WAIT_GRASP_STABLE` takes the bypass.

**Recommended boundary**

Restore only the missing success edge. Do not change micro-lift distance, contact policy, physical thresholds, motion targets, or recovery routes to make the restored gate pass.

### P1: force-continue is declared and exposed but the common runner cannot park or consume it

**Fact**

- `src/pick_place_common/include/pick_place_common/workflow_definition.hpp:17-25` exposes `force_continue_states`, and SO-101 declares `VALIDATION_FAILED` in that set.
- `src/pick_place_common/src/run_request_validation.cpp:63-65` checks only that force-continue is an execute resume.
- `src/pick_place_common/src/runner.cpp:323-330` hard-codes `State::VALIDATION_FAILED` and always returns `CHECKPOINT_COMPLETE`, ignoring `request.force_continue` and the workflow declaration.
- `src/pick_place_common/src/runner.cpp:564-570` and `612-614` send action/postcondition failures to normal recovery; no code persists the documented forward validation-failure checkpoint.
- `src/pick_place_common/src/runner.cpp:660-672` accepts only the success edge for a forward checkpoint, so a checkpoint describing `VERIFY_PHYSICAL_GRASP --failed--> VALIDATION_FAILED` is rejected before the SO-101 resume policy can validate it.
- `src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp:104-107` parses `--force-continue`.
- `src/so101_gazebo_demo/so101_teleop/server.py:648-659` sends the flag and reports a successful package-CLI request, but the flag cannot advance the C++ runner.
- C++ runner tests cover request shape and workflow declaration only; the web gateway tests use a fake runner that assumes override progression.

**Impact**

After the physical-grasp chain is restored, a failed validation either enters recovery instead of parking or cannot be advanced by the operator-approved override. The UI can report a successful command without the C++ workflow consuming the override. Common also leaks a robot-specific state name into the runner.

**Trigger**

A physical-grasp postcondition failure followed by normal resume or `--force-continue` execute-resume.

**Recommended boundary**

Make the common runner interpret `WorkflowDefinition::force_continue_states` generically. Only a `POSTCONDITION` failure whose declared failed edge targets one of those states may park. Robot-specific code and the existing SO-101 resume validator continue to decide which failure codes and world evidence are valid. Panda declares no force-continue state and must remain behaviorally identical.

### P1: physical-grasp evidence is process-local, so Teleop single-step cannot reach verification

**Fact**

- `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp:497-504` stores the two physical-grasp windows in an in-memory `PhysicalGraspEvidence` object.
- Lines 620-624 write `before_lift` or `after_lift` only into that object; lines 751-756 fail with `PHYSICAL_GRASP_EVIDENCE_INCOMPLETE` unless both values are present in the same process.
- `src/so101_gazebo_demo/so101_teleop/server.py:477-495` implements every owner request as a new `subprocess.run` invocation.
- `src/so101_gazebo_demo/so101_teleop/server.py:648-656` invokes that package CLI separately for Start, Next Step, Resume, and Force Continue.
- No checkpoint field, sidecar, or robot evidence store persists the two windows across those invocations.

**Impact**

Once the skipped states are restored, a continuous CLI run can retain both samples, but the documented Teleop single-step workflow loses the first sample at process exit and must fail at `VERIFY_PHYSICAL_GRASP`. The fake Python gateway tests cannot reveal this lifetime mismatch.

**Trigger**

Any workflow that uses `--step`, exits, and resumes across `WAIT_GRASP_STABLE`, `MICRO_LIFT`, `WAIT_MICRO_LIFT_STABLE`, and `VERIFY_PHYSICAL_GRASP`.

**Recommended boundary**

Add a robot-local, session/fingerprint-bound physical-grasp evidence sidecar derived from the checkpoint path. Keep the common checkpoint schema unchanged. The stable-window actions atomically persist minimal historical samples; verification reloads and validates them. A fresh non-resume run clears stale sidecar data, while resume rejects mismatched session, fingerprint, state order, or malformed evidence.

### P2: `RunRequest` breaks the robot packages' positional aggregate source compatibility

**Fact**

- Before the refactor, both robot request structs began with `mode`, `stop_after`, `resume`, `fail_at`, and `max_state_transitions`.
- `src/pick_place_common/include/pick_place_common/domain_types.hpp:98-108` inserted `plan_only_state` between `stop_after` and `resume` while both robot headers now alias this public common type.
- Compiling the former SO-101 expression `RunRequest{RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100}` against the installed R2 headers fails because the third positional argument is now `std::optional<State>`.
- Current in-tree callers mostly use named assignment, so the three-package tests do not detect the external source break.

**Impact**

Out-of-tree source consumers of either robot package can no longer rebuild even though the compatibility headers and public type names remain present.

**Trigger**

Any positional aggregate initialization written against the pre-refactor field order.

**Recommended boundary**

Keep `RunRequest` an aggregate and move `plan_only_state` to the end. Add compile-time/source-contract tests for the former Panda five-field and SO-101 seven-field forms. Do not add constructors or implicit conversions.

### P2: Panda installs a dead state-machine bypass executable

**Fact**

- `src/panda_gazebo_demo/CMakeLists.txt:151-180` builds `attach_and_lift_demo`, and lines 454-462 install it as a public executable.
- `src/panda_gazebo_demo/src/attach_and_lift_demo.cpp:18-210` directly attaches/detaches the MoveIt object and can execute a Cartesian lift outside the checkpoint, recovery, Gazebo/MoveIt convergence, and runner-policy path.
- Repository search finds no current script, test, launch file, README, or docs consumer outside its own source and CMake declaration.
- Its only helper, `headless_fault_fixture.hpp`, is otherwise exercised only by three isolated unit tests and has no runtime consumer.

**Impact**

The package exposes a stale, unsafe-looking alternate execution entry point that can mutate only the MoveIt side and bypass the architecture documented in `docs/pick-place-architecture.md`.

**Trigger**

An operator discovers and invokes the installed executable, or a future test starts relying on it instead of the supported state machine.

**Recommended boundary**

Remove the executable, its private fault-fixture helper, and only the helper-specific tests/CMake entries. Preserve all current Panda state-machine runtime and headless acceptance scripts.

### P3: SO-101 Teleop retains an explicitly unused pose callback

**Fact**

- `src/so101_gazebo_demo/so101_teleop/server.py:210-220` defines `_legacy_bridge_pose_unused`.
- Repository search finds no subscription, direct call, test, or documentation reference to that method.
- The active `/so101/gazebo_pose_info` subscription uses `_on_gazebo_pose` instead.

**Impact**

The callback duplicates object-pose mutation logic without locking and obscures which observation path is authoritative.

**Recommended boundary**

Delete the unused method only. Keep the `TFMessage` import because the active pose subscriber still uses it.

## 3. Goals

1. Reconnect the SO-101 physical-grasp validation states before any attachment.
2. Implement safe, declaration-driven validation parking, normal resume, and one-shot force-continue in the common runner.
3. Preserve physical-grasp evidence across continuous and subprocess-per-step workflows without moving robot evidence into common.
4. Preserve failure, checkpoint, session, provenance, transition, and side-effect semantics across fresh and resumed requests.
5. Restore source compatibility for pre-refactor positional `RunRequest` aggregate initialization.
6. Remove the two verified dead-code surfaces.
7. Bring architecture, launch-parameter, SO-101, and Panda documentation into agreement with the installed behavior.

## 4. Non-goals

- No weakening of physical-grasp thresholds, contact requirements, R1 recovery-skip predicates, or resume validators.
- No new plan-only targets and no force-continue support in plan-only mode.
- No common checkpoint schema version change, session-ID migration, or provenance fallback. A robot-local evidence sidecar is in scope only with exact session/fingerprint/state binding.
- No new Panda force-continue or physical-grasp policy.
- No rewrite of the common state enum, runner architecture, ROS adapters, Teleop UI, or server command model.
- No real-robot execution.
- No merge, push, or changes to `codex-cua` as part of the document phase.

## 5. Approaches considered

### Approach A — declaration-driven common pause plus robot-local evidence sidecar (recommended)

The workflow declares its pause state and failed edge. The common runner parks only postcondition failures that target a declared force-continue state, validates the resulting checkpoint through the existing common plus robot resume policies, and consumes the override only when the loaded checkpoint names that state. SO-101 persists the two historical grasp samples in a robot-local sidecar bound to the checkpoint path, session, fingerprint, and state order.

**Advantages:** minimal common API growth; removes the hard-coded SO state; preserves Teleop step semantics; Panda remains unchanged; common checkpoint schema stays stable.
**Trade-off:** SO-101 owns one additional atomic temporary artifact that must be validated and cleaned.

### Approach B — checkpoint schema v4 plus more virtual runner decisions

Put physical samples into a new common checkpoint schema and add methods such as `shouldParkFailure` and `allowForceContinue` to the runner policy.

**Advantages:** one persistence artifact and maximum per-robot flexibility.
**Trade-offs:** makes common understand robot-specific evidence, requires schema migration, expands the R2 policy interface, and changes Panda serialization for no Panda benefit.

### Approach C — collapse the probe into one SO-101 wrapper action

Run stable-before, micro-lift, stable-after, and verification atomically in a wrapper or Teleop-only command, then special-case override outside common.

**Advantages:** no new persistence file.
**Trade-offs:** destroys the declared state/step contract, creates a second transition owner, and leaves direct common-runner force semantics broken.

Approach A is selected. B is unnecessary for the verified behavior; C is rejected as an abstraction leak.

## 6. Detailed design

### 6.1 SO-101 forward path

The success chain becomes:

```text
CLOSE_GRIPPER
  -> WAIT_GRASP_STABLE
  -> MICRO_LIFT
  -> WAIT_MICRO_LIFT_STABLE
  -> VERIFY_PHYSICAL_GRASP
  -> ATTACH_GAZEBO
  -> ATTACH_MOVEIT
  -> LIFT
```

Dry-run traces and deep plan-only predecessor traces must contain all four grasp-validation states. Their existing executors, contracts, policies, and recovery failed edges remain robot-owned.

### 6.2 Durable physical-grasp evidence across process boundaries

SO-101 adds a robot-local interface and file implementation:

```cpp
struct PhysicalGraspEvidenceRecord {
  std::string simulation_session_id;
  std::string configuration_fingerprint;
  std::optional<PhysicalGraspSample> before_lift;
  std::optional<PhysicalGraspSample> after_lift;
};

class IPhysicalGraspEvidenceStore {
public:
  virtual ~IPhysicalGraspEvidenceStore() = default;
  virtual std::optional<Failure> resetForFreshRun() = 0;
  virtual std::optional<Failure> saveBefore(const WorldSnapshot &) = 0;
  virtual std::optional<Failure> saveAfter(const WorldSnapshot &) = 0;
  virtual std::variant<PhysicalGraspEvidenceRecord, Failure> load() const = 0;
};
```

`PhysicalGraspSample` stores only the historical inputs used by `PhysicalGraspValidator`: TCP pose, Gazebo task-object pose, gripper contact, capture state, and capture time. The file schema is robot-local version 1 and contains the simulation session, policy-bundle fingerprint, and ordered states. It is written with temporary-file, `fsync`, atomic rename, and parent-directory `fsync`, following the existing SO-101 checkpoint durability pattern.

The path is the checkpoint path plus the literal suffix `.physical-grasp.json`; for example, `/tmp/so101-r3-step-checkpoint.json.physical-grasp.json`. A fresh request (`resume=false`) removes or resets it before execution. Resume never creates missing evidence and rejects malformed files or mismatched session/fingerprint/state ordering with stable `PHYSICAL_GRASP_EVIDENCE_*` codes. `WAIT_GRASP_STABLE` saves `before_lift`; `WAIT_MICRO_LIFT_STABLE` requires before and saves after; `VERIFY_PHYSICAL_GRASP` loads both. Continuous execution uses the same store, so continuous and subprocess-per-step semantics are identical.

The sidecar is not a substitute for the checkpoint. It cannot select a state, authorize resume, or survive a new session. A unique Teleop checkpoint path already provides workflow isolation. After successful verification it may remain as audit evidence until the next fresh run/reset; it is ignored once the checkpoint advances beyond the validation segment.

### 6.3 Parking a validation failure

After an action is stopped and a fresh stationary snapshot is available, common may park instead of recovering only when all conditions hold:

1. the workflow failed edge from the attempted state targets a member of `force_continue_states`;
2. the original failure category is `POSTCONDITION`;
3. the checkpoint store and resume validator are present;
4. the stopped snapshot is complete enough for the robot checkpoint codec and resume policy.

The persisted schema-v3 checkpoint remains `FORWARD` and `EXECUTE`, is resumable, and records:

- `last_completed_state=VERIFY_PHYSICAL_GRASP` for compatibility with the existing schema;
- `failed_state=VERIFY_PHYSICAL_GRASP`;
- `original_failure` unchanged, including all physical metrics;
- `next_state=VALIDATION_FAILED`;
- expected world state, exact simulation session, configuration fingerprint, and next sequence.

The result is `CHECKPOINT_COMPLETE`, current state `VALIDATION_FAILED`, the same original failure, and a trace ending in `VERIFY_PHYSICAL_GRASP -> VALIDATION_FAILED`. No recovery, Gazebo attach, MoveIt attach, planner, or controller request may occur after the failed verification.

Action, controller, observation, planning, environment, and recovery failures keep their current recovery/error behavior. A workflow that declares no force-continue states cannot enter this path.

### 6.4 Resume matrix

| Loaded checkpoint | Request | Required result |
|---|---|---|
| normal forward | execute resume, no override | existing resume behavior |
| normal forward | execute resume + force-continue | `FORCE_CONTINUE_STATE_MISMATCH`; no side effect or checkpoint write |
| recovery | execute resume + force-continue | `FORCE_CONTINUE_STATE_MISMATCH`; original recovery checkpoint unchanged |
| validation pause | execute resume, no override | `CHECKPOINT_COMPLETE` at the same pause state, same failure, checkpoint bytes unchanged, no side effect |
| validation pause | execute resume + force-continue | validate the exact session/fingerprint/world snapshot, consume the declared success edge, then execute from `ATTACH_GAZEBO` |
| any checkpoint | plan-only + force-continue | existing `FORCE_CONTINUE_REQUEST_INVALID` |

The common compatibility check accepts a forward checkpoint whose `last_completed_state --failed--> next_state` targets a declared force-continue state and carries both `failed_state` and `original_failure`. All other forward checkpoints still require the success edge.

For a validation pause, resume validation first compares the parked expected world to the live world. Normal resume performs no write. Force-continue validates the `VALIDATION_FAILED -> ATTACH_GAZEBO` contract, then clears the parked failure from active recovery context before executing attachment. The Teleop override audit remains the durable operator-confirmation record.

`single_step=true` remains honored: force-continue consumes the pseudo-state transition and executes one real state (`ATTACH_GAZEBO`), leaving a normal checkpoint for `ATTACH_MOVEIT`. Full force-continue runs forward until the next checkpoint/terminal/failure under existing controls.

### 6.5 Failure, transition, and checkpoint invariants

- The parked checkpoint preserves the original `PHYSICAL_GRASP_*` failure byte-for-byte through a normal resume.
- Normal resume at the pause state has transition count 0 and trace `{VALIDATION_FAILED}`.
- The attempted verification is counted once when it parks; returning the passive pause result does not add a transition.
- A force-continue pseudo-transition is counted once; each subsequently executed state keeps the existing one-transition count.
- Force-continue cannot be replayed after `ATTACH_GAZEBO` commits its next normal forward checkpoint.
- A force-continue failure before attachment leaves the parked checkpoint unchanged.
- No R1 state-aware recovery-skip condition or original-failure behavior changes.
- Continuous execution and subprocess-per-step execution produce the same physical metrics and pass/fail result for the same observations.
- A missing, corrupt, stale-session, wrong-fingerprint, or out-of-order sidecar fails closed before attachment and cannot be force-continued as a valid physical failure. Evidence-store failures use checkpoint/resume-validation or internal categories, never `POSTCONDITION`; only the validator's own `PHYSICAL_GRASP_*` postcondition can park at `VALIDATION_FAILED`.

### 6.6 Common/robot boundary

Common owns:

- recognizing declared pause states;
- generic request/checkpoint compatibility;
- checkpoint persistence and passive resume;
- consuming a validated pause-state success edge;
- trace and transition-count bookkeeping.

SO-101 owns:

- the `VALIDATION_FAILED` declaration and edges;
- `PHYSICAL_GRASP_*` evidence and thresholds;
- resume acceptance for exact physical failure codes and world state;
- the `VALIDATION_FAILED -> ATTACH_GAZEBO` transition contract;
- the robot-local physical-evidence sidecar codec, durability, session/fingerprint binding, and lifecycle;
- Teleop confirmation and audit.

Panda continues to declare an empty force-continue set and uses the characterized default runner policy.

### 6.7 Public request compatibility

`RunRequest` remains an aggregate. Its original field prefix is restored:

```cpp
RunMode mode;
std::optional<State> stop_after;
bool resume;
std::optional<State> fail_at;
std::uint64_t max_state_transitions;
bool single_step;
bool force_continue;
std::optional<State> plan_only_state;
```

All in-tree construction continues to use named assignment. The new source-contract test compiles the historical Panda five-field and SO-101 seven-field forms and verifies the mapped values.

### 6.8 Dead code and documentation

Remove:

- `src/panda_gazebo_demo/src/attach_and_lift_demo.cpp`;
- its CMake executable, dependency, quality-gate, and install entries;
- `headless_fault_fixture.hpp` and only its three `HeadlessFaultFixture` tests;
- `SO101TeleopNode._legacy_bridge_pose_unused`.

Update the architecture and launch manual to state the restored validation chain, parking semantics, normal resume behavior, force-continue matrix, and the fact that a deep plan-only run must pass physical validation naturally. Do not document force-continue as a way to preserve plan-only mode.

## 7. Migration and integration

R2 is currently 11 commits behind the reviewed `origin/main`, with overlap in SO-101 CMake, package manifest, and README files. R3 implementation must not begin on a stale independent branch.

The implementation start gate is:

1. R2, including this R3 document commit, has been integrated into `origin/main` by the user-approved merge workflow;
2. a fresh `codex/refactor-optimization-r3` worktree is created from that updated `origin/main`;
3. package prefixes and build/install paths resolve only to the R3 worktree.

The executor discovers the integrated document commit with `git log -1 --format=%H origin/main -- docs/superpowers/specs/2026-08-05-refactor-optimization-r3-design.md docs/superpowers/plans/2026-08-05-refactor-optimization-r3-implementation.md`, requires a non-empty result, and runs `git merge-base --is-ancestor "$document_commit" origin/main`. If either check fails, implementation stops and reports that R2 integration is still pending. The R3 executor must not silently rebase or merge the 41-commit R2 branch.

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Restored physical validation exposes a real grasp/calibration failure | Treat it as a valid safety failure; do not weaken thresholds. Preserve evidence and stop for a new robot-policy decision. |
| Generic pause logic parks unrelated failures | Require both a declared failed-edge target and `POSTCONDITION`; robot resume policy validates exact codes. Add negative action/controller/observation tests. |
| Force-continue replays or writes before validation | Reject mismatched checkpoints, validate live world first, and keep bytes unchanged until the override is consumed by a real successful state. |
| Sidecar is stale, corrupt, or paired with another workflow | Bind it to exact checkpoint path, session, fingerprint, capture states, and finite samples; write atomically; fail closed before attachment. |
| Continuous and step modes diverge | Use the same evidence-store interface in both modes and run A/B runtime acceptance on identical observations. |
| Panda behavior changes through common runner edits | Run characterization, three-package tests, Panda plan-only/resume matrix, recovery scenarios, and GUI runtime regression. |
| Aggregate reordering breaks new positional R2 callers | There are no in-tree positional R2 callers; require named assignment for new fields and test the pre-refactor public prefix. |
| Deleting the fault fixture removes a hidden dependency | Repository-wide reference scan and installed executable contract must go RED before removal and GREEN afterward. |

## 9. Acceptance rules

### 9.1 Automated RED -> GREEN

1. A SO-101 characterization test initially fails because the expected trace now requires `MICRO_LIFT`, `WAIT_MICRO_LIFT_STABLE`, and `VERIFY_PHYSICAL_GRASP`.
2. Common runner tests initially fail for validation parking, passive resume, force consumption, mismatch rejection, original-failure preservation, checkpoint bytes, trace, transition count, and negative failure categories.
3. SO-101 evidence-store and subprocess-lifetime tests initially fail because both physical windows exist only in process memory.
4. A source-compatibility compile test initially fails with the historical positional aggregate forms.
5. A Panda package-contract test initially fails while `attach_and_lift_demo` remains built/installed.
6. Teleop source test initially fails while `_legacy_bridge_pose_unused` exists.

All targeted tests must pass after the smallest implementation.

### 9.2 Build and package tests

From the isolated R3 worktree:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo \
  --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
```

Required: 0 errors and 0 failures; no regression in the prior 1,152-test baseline except intentional removal/addition counts documented in evidence.

### 9.3 SO-101 runtime

Use a fresh ROS domain, Gazebo partition, simulation session, checkpoint, and evidence directory.

1. Execute through physical validation without failure injection in one continuous process. Before `ATTACH_GAZEBO`, observe the micro-lift TCP delta, cup-follow ratio, table clearance, contact, XY slip, orientation delta, and PASS result. If the real gate fails, stop; do not force thresholds.
2. Repeat the same segment through separate `--step` subprocesses. Verify the sidecar is atomically created, both samples bind to the same session/fingerprint, and the physical result matches the continuous run.
3. Inject a deterministic `PHYSICAL_GRASP_*` postcondition failure using a test-owned physical observer/evidence fixture against the live R3 stack; do not alter production thresholds. Verify the checkpoint parks at `VALIDATION_FAILED`, retains the original metrics/session/fingerprint, and both Gazebo and MoveIt remain detached/world-only.
4. Run execute-resume without force. Verify checkpoint and sidecar bytes, failure, trace, joints, TF, controllers, Gazebo pose/attachment, and MoveIt membership remain unchanged.
5. Run an invalid force-continue against a normal forward and a recovery checkpoint. Verify `FORCE_CONTINUE_STATE_MISMATCH` and zero side effects.
6. Run valid force-continue with `single_step=true`. Verify exactly `ATTACH_GAZEBO` executes, Gazebo becomes attached, MoveIt remains world-only, the next checkpoint is `ATTACH_MOVEIT`, and the original override evidence remains in the Teleop audit.
7. Resume normally and finish the workflow; verify Gazebo and MoveIt converge after attach and detach, joints/TCP reach their targets, and the final cup pose is supported.

### 9.4 Panda runtime

Run the existing six-target plan-only/resume matrix, recovery scenarios, and one fresh GUI execute regression from the R3 overlay. Required: all targets/scenarios pass, no new force-continue state exists, and `ros2 pkg executables panda_gazebo_demo` does not list `attach_and_lift_demo`.

### 9.5 Visual, provenance, and cleanup

- Capture fresh before, validation-pause, post-force-continue, and final screenshots; inspect each image rather than checking file existence.
- Record `ros2 pkg prefix` for all three packages, executable paths, `AMENT_PREFIX_PATH`, source commit, branch, and install timestamps.
- Confirm no root-workspace build/install prefix is used.
- Clean only owned R3 ROS/Gazebo/MoveIt processes and recheck PIDs, ROS nodes, tmux windows, domain, and partition.
- Worktree must be clean with scoped commits, `git diff --check` must pass, and no merge, push, or `codex-cua` interaction may occur during implementation acceptance.

## 10. Stop conditions

Stop and request a new user decision if any of the following occurs:

- R2/R3 document commit is not yet integrated into latest `origin/main`;
- restoring the chain reveals a persistent physical-grasp failure that can only be made green by changing thresholds, geometry, motion, or contact policy;
- safe force-continue requires a common checkpoint schema, session identity, or provenance fallback beyond the approved robot-local sidecar;
- Panda gains a force-continue state or changes its characterized trace/recovery behavior;
- runtime and visual evidence disagree after one isolated rerun;
- a ROS/Gazebo/MoveIt process cannot be safely attributed before cleanup.
