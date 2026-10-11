"""The coarse-step val sweep: the raw observations, the decision, and the evidence phase 6 owns.

Design section 7.1 gives `coarse_step_rad` one rule: among the candidates at or below half the horizontal
field of view, take the **largest** step whose bounded two-way sweep covers the whole
`required_search_domain_rad` and misses no required-visible val cup, and never replace the coverage proof
with a fixed forward accumulation. Phase 2 generates the candidates, proves the coverage and issues the
per-target sweep-check receipts; this module owns the other half of the rule - the val evidence - and
turns a raw sweep into the value and the evidence block phase 6 hands to phase 8.

The raw observations are exactly that, raw: one entry per generated candidate step, per val scene, per
anchor and per bounded stop, carrying that stop's per-camera ground truth and the selected model's
detections (the recorder semantics). **This module never trusts a declared
verdict**: it re-derives the bounded plan of every candidate from the sealed geometry (the repository's
own `bounded_search_stops` and `independent_sweep_check`), requires the recorded stops to be that plan,
matches the detections to the truth itself with the gate's greedy nearest rule, and decides from those
numbers. A cup the sweep's own stops see but never detect is a missed scene; a scene the dataset declares
empty is not required-visible; two passes that disagree are contradictory evidence rather than a result.

Four refusals, all of them fail-closed and none of them inventing a value:

* `CAL_SWEEP_EVIDENCE_MISSING` - nothing was measured at all (no raw document, no candidate, no scene);
* `CAL_SWEEP_EVIDENCE_PARTIAL` - the measurement grid is incomplete: a generated candidate step was not
  measured, a candidate was measured on a different scene set, or an anchor or a stop of its own bounded
  plan is missing;
* `CAL_SWEEP_EVIDENCE_CONTRADICTORY` - the document contradicts itself or the run: its declared digest is
  not its body, its geometry or camera domain is not the sealed one, it carries evidence of another model
  than the selected one, its stops are not the bounded plan, or two passes of the same scene disagree;
* `CAL_SWEEP_UNSTABLE` - the evidence is complete and consistent, but no candidate step both covers the
  required domain and locks every required-visible val scene. Design section 7.1 has no value to report in
  that case, so the phase reports the failure instead.

Evidence from another split is refused with phase 3's own `CAL_SPLIT_LEAK` (the val split is the only one
this parameter may be measured on), and a startup readback that disagrees with the value is refused with
phase 8's `CAL_EFFECTIVE_VALUE_MISMATCH`, both reusing the existing codes rather than inventing new ones.

The module also owns the **producer**: :func:`measure_coarse_step_val_sweep` drives the repository's
dataset renderer over the head val scenes and the selected model over every bounded stop of every
generated candidate, and writes the raw observations and the decision. That is the only place in this
module that imports MuJoCo, the detector or a GPU, and it does so inside the function, so the decision
layer stays a pure, independently testable library. The CLI only parses and validates: the measurement is
the installed program's, never an ad-hoc script's.
"""
