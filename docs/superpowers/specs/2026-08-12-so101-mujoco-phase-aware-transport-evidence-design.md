# SO-101 MuJoCo Phase-Aware Transport Evidence Design

**Date:** 2026-08-12

**Status:** Approved by the user, including the local-review amendments in this document

**Behavior baseline:** `8f71442ae6cff43e0770eec929b13211d2057628`

**Prior evidence:** EXP-109 at `a172765e3b193bfccad9782d02e2745e70f1cbd2`

## 1. Purpose and authority

EXP-109 proved that the frozen five-win strategy reaches transport after passing contact hold,
micro-lift, and all formal lift waypoints. It also exposed a contract error: the runtime applied
the approved static maximum force, `1.1579004532160448 N`, as a hard stop during dynamic
transport. Historical successful runs show that the same frozen strategy normally crosses that
static value during transport.

This design separates static-contact acceptance from dynamic-transport diagnostics. It authorizes
only measurement, logging, analysis, disabled-proposal generation, and the minimum typed runtime
wiring needed to observe or safely abort diagnostics. It does not authorize any behavior change to
the successful grasp or motion strategy.

The following are frozen without exception:

- seating preload `q6=-0.04850794875050089`;
- every q6 target, approach/lift/transport/place/retreat waypoint, trajectory input, planner,
  planning time, velocity scaling, acceleration scaling, start state, and phase order;
- MJCF, task scene, geometry, URDF, controller configuration, simulator initial state, and normal
  execution semantics;
- the protected `src/so101_gazebo_demo_py` tree, which must remain unchanged.

No compensation, force filtering, delay, grace period, replanning, or waypoint mutation may be
introduced. Project B/C/D, the formal nine-stage regression, RESET_WORLD five-win challenge,
merge, and push remain prohibited until the new exact-hash proposal is explicitly approved.

## 2. Existing evidence defect

The task scene uses a `0.002 s` MuJoCo timestep, or 500 physics steps per second. The current
`SimulationEvidencePlugin` publishes ordinary snapshots at 100 Hz and skips a publication when
`RealtimePublisher::trylock()` fails. Its current `simulation_step` increments only while a
snapshot is successfully built. It therefore describes successful publications, not every
physics step.

Consequently the current evidence cannot support claims of an instantaneous physics-step peak,
an unbroken force trace, or a same-step `11.60 N` stop. Python polling cannot reconstruct missing
physics steps. Phase-aware transport evidence is valid only after this defect is corrected at the
plugin/physics boundary.

## 3. Evidence architecture

### 3.1 Two publication paths

The existing 100 Hz `SimulationEvidence` snapshot remains for backward-compatible observers. Its
`simulation_step` becomes the true current physics-step index rather than a publish counter;
`publisher_sequence` remains the snapshot publication sequence.

A new lossless diagnostic path records one `PhysicsStepEvidence` for every advancing MuJoCo
physics step. The plugin builds this record inside `update()` directly from the locked `mjModel` /
`mjData` boundary. Samples are accumulated into `PhysicsStepEvidenceChunk` messages. Every chunk
contains the immutable session and reset identities, first and last physics steps, first and last
simulation times, failed publish-attempt count, evidence-loss latch, and an ordered array of step
samples.

The normal flush cadence is five physics steps, matching the existing 100 Hz publication cadence.
A failed `trylock()` does not discard samples: the queue remains intact and the next successful
publish covers the complete continuous range. The queue is bounded. Reaching its bound latches
`evidence_loss`; it never silently overwrites an older step. A run containing evidence loss,
truncation, a missing or repeated step, or an unclosed range is `INVALID` and stops the batch.

### 3.2 Per-step sample

Each physics-step sample carries:

- `physics_step`, `simulation_time_s`, `reset_epoch`, and `simulation_session_id`;
- object pose and twist at that step;
- the existing raw left-fingertip, right-fingertip, and allowed-other contact arrays;
- `truncated` and all tracked-contact identities needed for replay;
- `maximum_normal_force_n`, preserving the existing meaning: the largest single normal force
  among all tracked cup contacts;
- `left_fingertip_total_normal_force_n` and `right_fingertip_total_normal_force_n`, each the sum of
  single-contact normal magnitudes on its whitelist side;
- `fingertip_max_single_contact_force_n`, the maximum over the two fingertip arrays;
- `global_max_single_contact_force_n`, an explicit alias of the existing
  `maximum_normal_force_n`; equality is validated;
- left and right fingertip compression, each `max(0, -minimum signed distance)` over only the
  cup-to-whitelisted-fingertip contact pairs;
- the net tracked-contact force vector on the cup, computed by summing each contact's recorded
  force-on-cup normal vector multiplied by its normal-force magnitude;
- static-shadow crossing and diagnostic-hazard latch fields.

Table and other-object contacts never enter fingertip compression. Any truncated contact array
makes the run invalid because neither the maximum nor summed/vector metrics remain provable.

### 3.3 Hazard latch and reaction bound

The diagnostic hazard is `global_max_single_contact_force_n >= 11.60`. Equality is a breach. The
plugin latches the first breach at the same physics-step boundary and preserves its step, simulation
time, force, session, and reset epoch. Later frames cannot clear or replace it.

The physics plugin cannot prove that MoveIt has stopped within the same 2 ms step. It therefore
makes the narrower claim that detection and notification publication are requested from the
breaching physics callback. The transport process requests trajectory cancellation when the typed
hazard notification is received. The live contract records the cancellation-request physics step
and requires it to be no more than 25 physics steps, or `0.050 s`, after the breach step. A breach
within this bound produces experiment `status: VALID` with
`outcome_class: VALID_SAFETY_ABORT`, preserves partial evidence, and stops all five-run sampling. A
later request, missing notification, or evidence gap is `status: INVALID`; it still triggers
best-effort cancellation and stops the batch. No same-step-stop claim is permitted.

## 4. Typed phase boundary

Force handling is selected by a typed `ContactForceMode`, never a free-form string or an implicit
no-argument helper:

- `PRE_TRANSPORT_STATIC_HOLD`: the stationary bilateral confirmation before waypoint 1 goal
  dispatch. `maximum_normal_force_n > 1.1579004532160448` fails closed under the existing approved
  static-contact policy. The diagnostic hazard also remains active.
- `DYNAMIC_TRANSPORT_SHADOW`: begins at waypoint 1 `ExecuteTrajectory` goal dispatch and includes
  execution monitoring, every post-waypoint settle/stable window, inter-waypoint planning/hold,
  subsequent waypoints, and the final transport-outcome computation. Crossing
  `1.1579004532160448 N` is recorded only; it never cancels or classifies the strategy as failed.
  The `>=11.60 N` diagnostic hazard remains a hard abort.

The current `stable_bilateral()` use is split into an explicit typed helper. Unit tests must prove
that the pre-transport static call fails closed above the static threshold while every post-dispatch
call remains shadow-only at that threshold.

Phase and waypoint boundaries are written as typed events. The sample immediately before dispatch
is the static closing boundary; the next physics sample is the first dynamic sample. The dynamic
phase remains open through the final transport outcome. Every execution, settle, and inter-waypoint
hold subsegment has explicit start and end boundary samples; no integration crosses a phase or
waypoint boundary.

## 5. Metric definitions

All time calculations use MuJoCo simulation time and the observed `0.002 s` physics timestep.
Receipt wall time is diagnostic metadata only.

- `peak_global_max_single_contact_force_n` is the maximum per-step
  `global_max_single_contact_force_n` in a closed segment.
- `force_time_exposure_n_s` is the trapezoidal time integral of the global maximum-single-contact
  scalar. It is explicitly not object momentum or net physical impulse.
- `shadow_excess_force_time_exposure_n_s` is the trapezoidal integral of
  `max(maximum_normal_force_n - 1.1579004532160448, 0)`. It uses exactly the metric with the same
  semantics as the static threshold.
- `net_contact_impulse_vector_n_s` is the component-wise trapezoidal simulation-time integral of
  the per-step summed tracked-contact force vector on the cup. This is the only output called a
  physical contact impulse.
- A sustained-overpressure window is a maximal consecutive run of physics samples for which
  `maximum_normal_force_n > 1.1579004532160448`. There is no interpolation and no grace period.
  Each sample represents one physics interval, so duration is `sample_count * 0.002 s`. The record
  includes first/last step and time, sample count, peak, force-time exposure, and shadow-excess
  exposure.
- Left/right compression maxima are computed independently from their whitelisted fingertip pairs.
  Segment compression never includes the table or other tracked contacts.

Integrals operate only on adjacent samples with matching session/reset identity, consecutive
physics steps, strictly increasing simulation time by one timestep, and membership in the same
closed segment. Missing, duplicate, reversed, cross-reset, truncated, or boundary-incomplete data
invalidates the entire run and stops the batch.

## 6. Durable raw and partial evidence

The transport recorder writes content-addressed chunk files outside the repository. Each chunk is
first written to a temporary sibling, `fsync`ed, and atomically renamed. An atomically replaced run
index lists chunk ranges and SHA-256 values. Typed phase/waypoint boundary events are stored through
the same mechanism.

The recorder checkpoints after every received chunk and emits a closed waypoint checkpoint after
every post-waypoint stable window. Thus normal completion, `VALID_SAFETY_ABORT`, phase failure, or
abnormal shutdown retains every previously acknowledged complete chunk plus its hash. A partial
artifact is never promoted to valid unless all ranges up to its declared terminal boundary are
continuous and independently replayable.

## 7. Frozen-behavior audit

Before production code changes, the repository stores a canonical frozen-behavior manifest and a
SHA-256 file. It binds:

- the exact seating preload and transitional phase start/q6 expectations;
- all motion-policy approach, lift, transport, descend, place, release, retreat, and recovery
  targets and scaling through the complete motion-policy hash;
- transport AST-level semantic constants and `JointPlanRequest` / execution call arguments;
- runtime phase order and expected phase-status map;
- MJCF, scene, task scene, geometry-bearing URDF, planner, joint-limit, controller, and plugin
  configuration hashes;
- the protected Gazebo tree digest and zero-diff state.

After instrumentation changes, a semantic verifier parses the typed policy and relevant Python AST
and compares those behavior values and call semantics with the manifest. A restricted diff gate
allows only the named evidence messages/plugin, measurement modules, schema/analyzer/proposal code,
tests, transport measurement wiring, and experiment documents. Whole-file `transport.py` hash
equality is not required because instrumentation necessarily changes it; every frozen behavior
field is required to remain equal.

## 8. Five-run experiment design

EXP-110 through EXP-114 are five independent `FULL_RESTART` runs referencing EXP-109. Each run has
its own `PLANNED -> RUNNING -> VALID | INVALID` transition, ROS domain, Gazebo partition,
simulation session, reset epoch, evidence root, source/install/runtime provenance, raw and summary
hashes, physical transport outcome, cancellation/shutdown result, and owned-process cleanup.

Runs 1–4 are descriptive repeat runs. Run 5 is a preregistered replication, not a fitted holdout.
Only the five FULL_RESTART runs are independent experiment units. Waypoints are repeated measures
and stratified detail within a run; the report must not represent five runs times five waypoints as
25 independent samples.

Run 5 validates only:

- complete and replayable evidence under the identical frozen strategy;
- the existing physical transport-success contract;
- deterministic recomputation of every diagnostic metric.

No empirical dynamic range accepts or rejects run 5. A valid experiment whose outcome class is
`VALID_SAFETY_ABORT`, or any `INVALID` experiment, stops the whole batch without retry,
replacement, or hidden rerun.

## 9. Proposal and approval boundary

After five valid physical transport successes, the analyzer generates a deterministic schema-v4
proposal with:

- the already approved static threshold `1.1579004532160448 N` and its existing calibration
  provenance;
- `acceptance_role: diagnostic_only` for all dynamic transport results;
- explicit metric definitions and units;
- the five run summaries and waypoint/repeated-measure detail;
- raw chunk, summary, frozen-behavior, source, install, runtime, dependency, model, scene, policy,
  and provenance hashes;
- `approval.enabled: false`, no approver, and no dynamic acceptance threshold.

The `11.60 N` value is recorded only as the diagnostic safety-abort boundary. Proposal generation
does not activate, self-approve, or modify the checked-in formal runtime policy. Once the exact
proposal hash is generated, the ledger enters `USER_APPROVAL_REQUIRED` and all work stops pending
the user's approval of that exact hash.

## 10. Verification gates

Implementation follows strict RED -> GREEN cycles. Required tests include:

- a 500 Hz intermediate force spike survives the 100 Hz chunk flush cadence;
- failed `trylock()` attempts retain the full step range and are detectable;
- true physics steps and simulation time are continuous across chunks;
- `>=11.60 N`, including equality, latches once and cannot be overwritten;
- the notification is requested from the breach callback and live cancellation-request latency is
  at most 25 physics steps, without claiming same-step stop;
- typed static pre-hold versus dynamic shadow behavior;
- exact hand-derived scalar/vector exposure, overpressure windows, and fingertip-only compression;
- every invalidity condition, atomic partial checkpoint, schema-v1/v2/v3 read compatibility, and
  deterministic disabled schema-v4 proposal hashing;
- frozen-behavior semantic equality and protected Gazebo zero diff.

Before live sampling, focused tests, the complete Python package suite, Ruff check/format-check,
C++ format/lint checks without `--reformat`, a clean isolated three-package build/test, installed
overlay provenance, frozen-manifest verification, and protected-tree gates must all pass. A failed
automatic gate is fixed at the evidence implementation boundary; it never authorizes a live run.
