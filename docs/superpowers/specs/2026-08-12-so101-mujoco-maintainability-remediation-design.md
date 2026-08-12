# SO-101 MuJoCo Migration Maintainability Remediation Design

**Date:** 2026-08-12

**Status:** Approved architecture; written specification awaiting review

**Baseline:** `70bece06e008b27da8f0923472668e95a369309e` on
`codex/so101-mujoco-ros2-teleop`

## 1. Purpose

The migration has qualified one fixed MuJoCo pick-place implementation, but the
qualified path still contains incomplete policy approval, a second production
orchestrator outside the state machine, experiment-shaped subprocess phases,
duplicated policy values, stale qualification accounting, and Gazebo-specific
names in simulator-neutral contracts.

This remediation turns the qualified experiment into a maintainable production
implementation without weakening its physical-evidence boundary. It resolves
the seven audit findings in the approved order:

1. activate an explicitly approved contact and physical-outcome policy;
2. make the state machine, checkpoints, and bounded recovery own live execute;
3. provide real MoveIt plan-only behavior;
4. replace subprocess phase scripts with one typed in-process runtime;
5. establish one MuJoCo policy source and a Gazebo/MuJoCo parity gate;
6. make qualification gates clean and reproducible;
7. remove duplicated scripts, backend-specific core names, and stale docs.

## 2. Fixed constraints

- This work is simulation-only. It does not authorize real-robot motion.
- MuJoCo physical evidence remains the cup-motion truth. MoveIt attachment is
  only the Planning Scene collision shadow.
- No weld, equality, adhesion, mocap, object teleport, direct object-state
  write, or hidden retry may create or prove a grasp.
- The protected `src/so101_gazebo_demo_py` implementation is not copied into or
  imported by the MuJoCo package. Cross-backend parity is checked at repository
  test time, not through a runtime dependency.
- Existing CLI arguments remain accepted. Correct live semantics replace the
  current silent ignoring of execute-only arguments.
- Existing evidence, checkpoint, and HTTP consumers receive versioned
  compatibility adapters. Backend-specific spellings do not remain in new core
  models.
- Existing user changes and unrelated tmux/ROS processes are preserved.
- Remote operations use standard Git against Gitee `origin`; `gh` is not used.
- `ament_uncrustify --reformat` is prohibited. Web commands use Bun.

## 3. Selected architecture

The implementation is divided into four independently reviewable projects,
executed in order A, B, C, D. Each project has its own TDD cycles and ends in a
working, testable checkpoint. The old qualified path remains available until
the replacement passes behavioral equivalence gates; it is then deleted rather
than retained as a permanent fallback.

```text
CLI / launch / Teleop
        |
        v
StateMachineRunner  <---->  versioned CheckpointStore
        |
        v
LiveActionRegistry (one StateAction per workflow state)
        |
        v
LiveContext (one ROS node/executor, clients, observer, evidence writer)
        |
        +---- MoveIt planning and Planning Scene
        +---- ros2_control arm and gripper actions
        +---- MuJoCo atomic observer and reset provenance
        +---- approved TaskPolicy and pure outcome evaluators
```

`StateMachineRunner` is the sole transition owner in dry-run, plan-only, and
execute. `live_runtime.py` becomes a composition root, not a second state
machine. The runtime never launches per-phase Python subprocesses and never
uses environment variables or intermediate JSON files as phase-to-phase IPC.

## 4. Project A: policy and physical outcome

### 4.1 Policy artifacts

The policy boundary has three distinct artifacts:

- `contact_calibration.yaml` is the calibration report and approval record. Its
  schema-v3 report stores five physical calibration regimes, two unilateral
  rejection contracts, sample counts, quantiles, a physical-cohort confusion
  matrix, source evidence hash, model/config fingerprints, exact proposed
  thresholds, exact proposal hash, approval identity/time, and activation
  status.
- `motion_policies/light_cup_wall_pick.yaml` remains the sole source for named
  arm/gripper targets, velocity/acceleration scaling, tolerances, dwell times,
  and the physical final-target region used by MuJoCo.
- An immutable `TaskPolicy` object loads both files and records their SHA-256
  values. Every execute/checkpoint/evidence manifest carries these hashes.

The final-target region is `x=[-0.090, -0.070] m` and
`y=[-0.260, -0.240] m`, matching the current Gazebo validation policy and the
10 mm target-ring contract. MuJoCo code must not repeat these bounds.

The existing `11.60 N` value is treated as a diagnostic hazard ceiling, not as
proof of an approved operating threshold. It moves into policy data. The
approved operating limits are generated from fresh calibration evidence.

### 4.2 Approval lifecycle

Activation is deliberately two-stage:

1. Run a fresh, fixed-fingerprint physical calibration campaign for
   `no_contact`, `bilateral_touch`, `over_compression`, `micro_lift_slip`, and
   `stable_hold`, bind the `left_only` and `right_only` fail-closed contracts to
   their evidence dispositions, and produce a disabled proposal. The analyzer
   writes exact values and a proposal hash; it never self-approves.
2. Present the proposal, raw evidence hashes, distributions, safety margins,
   and misclassification results to the user. Only an explicit response that
   approves that exact proposal hash permits writing approval metadata and
   setting `approval.enabled: true`.

Activation metadata, including `enabled`, lives inside the `approval` envelope.
The proposal hash excludes that entire envelope and nothing else, so activating
an exact proposal cannot invalidate its own hash while every policy,
fingerprint, threshold, and statistical field remains hash-bound.

Any model, scene, motion-policy, calibration-evidence, or proposal-hash change
invalidates activation and fails execute closed. Plan-only loads motion policy
without activating contact execution; it still reports all fingerprints.

### 4.3 Calibration cohorts and unilateral contracts

Only five reachable physical regimes contribute samples to threshold fitting,
quantiles, held-out evaluation, and the physical misclassification matrix:
`no_contact`, `bilateral_touch`, `over_compression`, `micro_lift_slip`, and
`stable_hold`. Each requires at least 25 fresh raw samples. Within each regime,
samples are sorted by publisher sequence and every fifth sample is held out, so
the deterministic split retains at least 20 calibration and 5 evaluation samples
without depending on unrelated publisher-sequence residues or append timing.

The raw global `minimum_signed_distance_m` remains a whole-scene diagnostic and
may be dominated by allowed table support. Compression fitting, classification,
and the live grasp gate use the deepest left/right fingertip contact distance
only; allowed other-contact penetration must never be interpreted as fingertip
over-compression.

Slip is a temporal window decision, matching the live grasp evaluator: both
threshold fitting and held-out evaluation use the maximum object linear speed
over their respective per-regime split windows. Raw quantiles still describe
every atomic speed sample; no low-speed acceleration or decay sample is removed.
Because speed is a strictly non-negative scale metric and physical slip can span
orders of magnitude, its threshold is the geometric midpoint between the stable
window edge and slip-window peak. Force, compression, and duration retain their
linear separating thresholds.

`left_only` and `right_only` are deterministic rejection contracts, not
required physical calibration cohorts. Each contract records:

- the exact missing-side failure code and `stable_grasp_allowed: false`;
- a physical-evidence disposition of `observed` or `physical_unreachable`;
- immutable artifact hashes and experiment/ledger references when authentic
  evidence exists;
- `null`, never zero, for calibration count, evaluation count, and physical
  misclassification rate because no statistical cohort is claimed.

The collector accepts only the five physical regimes and cannot be used to
manufacture or label a unilateral campaign. Schema-v3 raw evidence carries the
two contract records beside the five physical regime arrays. The analyzer uses
`no_contact` as the zero-bilateral-force negative distribution and never uses a
contract record as a threshold sample. It emits physical-cohort confusion rows
only; predictions may still include all seven labels.

Typed unit fixtures and fault injection must prove that every left-only window
returns `GRASP_RIGHT_CONTACT_MISSING`, every right-only window returns
`GRASP_LEFT_CONTACT_MISSING`, and neither can become a successful stable grasp.
These fixtures are explicitly test evidence and are never serialized as raw
physical calibration samples.

The approved scope freezes the model, scene, geometry, simulator state,
planning axis, planner, q6 step, motion waypoints, 3 mm maximum pre-contact
displacement gate, 10 mm terminal-total-displacement gate, 11.60 N diagnostic
force gate, and the already qualified grasp strategy. A terminal total
displacement above 3 mm does not fail the pre-contact gate; only the driver's
independently monitored pre-contact field can do so.

### 4.4 Pure evaluators

New pure modules own physical decisions:

- `grasp_outcome.py` evaluates fresh bilateral contact, per-side force,
  compression/distance, forbidden contacts, dwell, session, and reset epoch.
- micro-lift evaluation requires causal TCP/cup motion, table clearance,
  bilateral contact continuity, bounded drift, bounded force, and no reset
  crossing.
- transport evaluation applies the same provenance and relative-pose contract
  over every lift, transfer, and descent segment.
- final placement evaluation consumes a new non-resumable release epoch and
  requires target-region position, table support, released gripper contacts,
  bounded pose/twist, MoveIt detachment, and world-object synchronization.

Evaluators consume typed samples and return typed results with a primary failure
code and metrics. They perform no ROS calls, file I/O, planning, execution, or
state mutation.

## 5. Project B: one live state-machine runtime

### 5.1 Runtime components

`LiveContext` owns one `rclpy` node and executor for the full workflow. It owns
joint-state subscription, the atomic MuJoCo observer, controller/action clients,
MoveIt planning/scene clients, TF access, policy fingerprints, evidence sequence
boundaries, and atomic artifact writing. Shared waiting, teardown, provenance,
and error conversion live here instead of being repeated by phases.

`LiveActionRegistry` maps every action state in `SO101_WORKFLOW` to a focused
`StateAction`. Motion actions read named policy targets. Observation actions
call the pure evaluators. Planning Scene actions attach or detach only the
collision shadow. Each successful action records evidence newer than its action
boundary before allowing the state transition.

`live_runtime.py` constructs `LiveContext`, `LiveActionRegistry`,
`FileCheckpointStore`, `RecoveryPolicy`, and `StateMachineRunner`, then returns
the normal `RunResult`. It does not own a separate `LIVE_PHASES` sequence.

### 5.2 Checkpoint and resume

Checkpoint schema v6 stores:

- state, next state, sequence, run/session identity, reset epoch;
- motion/contact policy hashes and model/scene fingerprints;
- known physical and Planning Scene side effects;
- last accepted evidence sequence and action boundary;
- release epoch state and whether resume is still permitted.

The loader accepts v4/v5 through a compatibility decoder and rewrites only on a
successful v6 commit. Resume rejects changed session, epoch, policy, model,
scene, stale evidence, inconsistent world/attached membership, and any
non-resumable release epoch.

### 5.3 Bounded recovery

Recovery is state- and evidence-dependent, not a fixed unconditional reverse
sequence:

- before physical grasp, the recovery policy selects bounded retreat/open
  actions only for effects proven to have occurred;
- after physical grasp and before release, an unsupported cup is never released
  automatically. The runtime stops/holds, records the observed outcome, and
  requires a separate reset transaction;
- after `DETACH_MOVEIT`, release/settle failures remain failures. Recovery may
  make the scene safe but cannot convert the result to `DONE`;
- every recovery action has a transition limit, evidence postcondition, and
  primary failure precedence. A recovery error is secondary metadata.

The simulator-neutral state name is `RECOVER_DETACH_SIMULATOR`. Legacy
`RECOVER_DETACH_GAZEBO` is accepted only by the v4/v5 checkpoint and CLI
compatibility decoder.

### 5.4 Removal of experiment runtime

The eight `live_phases/*.py` modules and their subprocess/environment/file IPC
are removed after the in-process path passes contract tests and one isolated
live equivalence cycle. The `staged_approach` console command becomes a
deprecated compatibility wrapper that invokes the state machine through the
`DESCEND` stop boundary; its independent ROS runtime is removed. There is no
permanent dual production implementation.

## 6. Project C: plan-only and compatibility

### 6.1 Real MoveIt plan-only

`--mode plan_only --plan-only-state <STATE>` uses the same live context and
policy target as execute, calls the real MoveIt planning boundary, validates the
returned trajectory and start state, and writes planning evidence. It sends no
arm trajectory, gripper command, scene mutation, reset, or simulator command.

Only states in `SO101_WORKFLOW.plan_only_states` are accepted. Unsupported or
non-motion states fail with a stable configuration error. Launch exposes
`dry_run`, `plan_only`, and `execute` consistently.

### 6.2 CLI semantics

Execute honors `--stop-after`, `--resume`, `--step`, `--force-continue`,
`--checkpoint`, `--max-state-transitions`, and session/policy arguments through
`RunRequest`. Test-only `--fail-at` remains restricted to dry-run/injected test
actions and cannot manufacture live failures in production.

`--force-continue` remains valid only at `VALIDATION_FAILED`, only when current
fresh evidence and policy explicitly permit it, and never bypasses physical
grasp or final-placement proof.

### 6.3 Versioned neutral contracts

The internal model uses only `simulator_detached`, `simulator_attached`, and
`RECOVER_DETACH_SIMULATOR`.

- Physical-outcome wire schema v5 emits `simulator_detached` and no
  `gazebo_detached` field.
- A v4 decoder accepts archived `gazebo_detached` evidence. A dedicated legacy
  serializer is available only where an identified v4 consumer still requires
  it; new code cannot call it implicitly.
- Teleop canonical camera routes are `/simulation/camera/presets` and
  `/simulation/camera/presets/{preset}`. The old `/gazebo/camera/...` routes are
  deprecated aliases over the same handler and remain for this compatibility
  release.
- OpenAPI and generated TypeScript expose canonical routes and mark aliases
  deprecated. UI code calls only canonical routes.

Compatibility tests prove both old inputs and new outputs. Core tests fail if
backend-specific names are reintroduced outside the compatibility modules,
Gazebo backend adapters, archived evidence, or historical documentation.

## 7. Project D: reproducible qualification and cleanup

### 7.1 Clean gate runner

A repository-owned qualification runner creates unique temporary build,
install, log, and test-result bases. It builds and tests exactly
`so101_mujoco_support`, `so101_mujoco_demo_py`, and `so101_teleop`, rejects stale
XML outside that base, and emits a machine-readable manifest with per-package
counts, skips, commands, exit codes, source/fork commits, overlays, and artifact
hashes.

The old `857 tests / 6 skipped` statement receives an explicit correction: it
included 240 stale Gazebo tests. Historical evidence is not silently rewritten.
The new report records only results generated by its clean run.

### 7.2 Isolation and documentation

The package isolation script remains canonical. The root script is replaced by
a small forwarding wrapper with no duplicated validation logic. Tests execute
the canonical implementation and prove the wrapper cannot drift.

The integration guide, qualification report, original-plan completion matrix,
and experiment ledger are updated together. Historical plans remain historical;
completion status is expressed through a dated evidence matrix that links each
requirement to current code, tests, and experiments.

### 7.3 Requalification

After all code and documentation gates pass, qualification freezes one commit
and one complete fingerprint. It then runs:

1. focused RED/GREEN tests and package tests;
2. Ruff, Bun/Vitest, clean isolated colcon build/test, runtime provenance,
   reset-qualified runtime, isolation, protected-Gazebo, hidden-constraint, and
   `git diff --check` gates;
3. real MoveIt plan-only for every supported motion state with proof that no
   actuator or scene mutation occurred;
4. one bounded stop/checkpoint/resume execute cycle;
5. five consecutive `FULL_RESTART` physical cycles;
6. five consecutive `RESET_WORLD` cycles on one stack with strictly increasing
   reset epochs;
7. one fresh GUI cycle and screenshot inspected through the project GUI skill.

Invalid infrastructure runs do not enter the denominator. `FULL_RESTART` and
`RESET_WORLD` results are never mixed. Every valid physical cycle independently
records MuJoCo cup/contact evidence, MoveIt attached/world state, controller and
joint convergence, final pose/twist, policy/model hashes, cleanup, and owned
process state.

## 8. Error and evidence rules

- Configuration/fingerprint errors fail before motion.
- Planning errors cannot be reported as execution or physical failures.
- Action success requires controller feedback and fresh joint/TF convergence;
  MoveIt success alone is insufficient.
- Physical evaluator failures retain their original failure code even if
  recovery also fails.
- Evidence is accepted only for the configured session, exact reset epoch,
  monotonic sequence after the action boundary, finite typed values, and current
  policy/model fingerprints.
- Release creates a fresh non-resumable epoch. Pre-release samples cannot prove
  settle or final placement.
- Manifests are written atomically and reference immutable artifact hashes.

## 9. Test design

All behavior changes follow strict RED-GREEN-REFACTOR. Tests assert behavior,
not source text or mocks.

Required test groups include:

- policy schema, proposal hash, approval/fingerprint invalidation, and exact
  activated-policy loading;
- schema-v3 five-regime physical evidence, immutable unilateral evidence
  dispositions, null missing-class statistics, and rejection of unilateral
  labels by the physical collector;
- typed and fault-injected left-only/right-only windows that deterministically
  fail with the corresponding missing-side code and can never prove a stable
  grasp;
- pure grasp, micro-lift, transport, and final-placement positive/negative
  matrices, including stale/reset-crossing and hidden-aid cases;
- state-machine live action registration, every stop boundary, single-step,
  resume, checkpoint migration, transition exhaustion, failure precedence, and
  bounded recovery;
- live plan-only trajectory validation and proof of zero actuator/scene calls;
- canonical v5 evidence, v4 decode compatibility, checkpoint v4/v5-to-v6
  migration, canonical HTTP routes, and deprecated aliases;
- single-source policy consumption and Gazebo/MuJoCo semantic parity;
- clean qualification result isolation and exact per-package accounting;
- launch, installed-entrypoint, runtime provenance, and cleanup contracts.

Mocks are limited to external ROS/MoveIt boundaries. Pure evaluators and policy
loaders use real objects and literal fixtures. Integration tests use the real
state machine and checkpoint store with only slow external actions replaced.

## 10. Completion contract

The remediation is complete only when all of the following are true:

- the activated contact policy contains fresh calibration evidence and explicit
  approval for the exact proposal hash;
- calibration thresholds and statistical quality claims are derived only from
  the five physical cohorts; unilateral contracts are evidence-bound,
  fail-closed, and never represented as zero-error missing cohorts;
- execute refuses disabled, stale, or fingerprint-mismatched policy data;
- `StateMachineRunner` is the only dry-run/plan-only/execute transition owner;
- every public execute control has tested live semantics;
- real MoveIt plan-only covers every supported motion state without mutation;
- no production phase subprocess/environment/JSON IPC implementation remains;
- MuJoCo runtime values come from one typed policy source and parity drift fails
  a repository test;
- new core schemas and routes are simulator-neutral while legacy inputs remain
  available only through explicit compatibility adapters;
- clean qualification statistics are reproducible from a unique result base;
- duplicated isolation logic and stale status documentation are removed;
- the frozen final commit passes all static, package, runtime, physical,
  repeatability, cleanup, and visual gates described above.
