"""The `aggregate` phase of the head search qualification: declared gates, and a refusal that names them.

This module is the phase the qualification plan calls ``aggregate`` (the last entry of
``head_search_qualification.RUN_PHASES``) and the phase ``head_search_scenarios.aggregate_scenarios``
names as the owner of the qualification verdict. It consumes the phase artefacts of a qualification run
and publishes a verdict **only if every declared gate holds**.

The gates are declared here, one constant at a time, and each one is evaluated against the artefact that
carries it - never against a summary of it:

======================  ==========================================================================
gate                    the artefact, and what it must show
======================  ==========================================================================
exclusive_ownership     the Step 1 ``EXCLUSIVE_OWNERSHIP_OK`` receipt whose ``planned_run_root`` is
                        **this** qualification run root, with the runtime of record it expected
runtime_identity        the frozen root of record read off disk: commit stamp, promoted config, the 17
                        approved values, the sealed weights, CUDA-only, no CPU fallback
approved_values_readback  the during-qualification readback: all 17 effective values and the four
                        camera measurements, taken under **this** run root, plus the approved bundle
                        whose values digest is the one the readback observed
scenario_journal        ``scenarios.json`` (self digest verified), ``scenario-journal.jsonl`` and one
                        per-scenario evidence document per declared seed, all 40 declared seeds
scenario_terminals      each scenario's terminal against the terminal statuses its condition class
                        declares (locked / expected-not-found / expected-ambiguous pass; anything else
                        fails), re-derived from the per-scenario evidence rather than read from the
                        producer's own ``outcome``
frame_cadence           the 10 Hz contract of every scenario: no duplicate, backward or undeclared gap
stop_proofs             every scenario's held stop proof: three consecutive qualifying samples
anchor_restarts         exactly one independent ``FULL_RESTART`` receipt per anchor, once each
production_smoke        the production smoke journal with its producer/sealed-journal/aggregator chain
teleop_acceptance       the separately owned Teleop acceptance receipt
======================  ==========================================================================

Missing or unreadable evidence is a refusal that **names the item**; it is never a pass and never a
silent skip. A gate whose evidence is present but does not hold is a violation. Both are reported
together, and the verdict is ``HEAD_SEARCH_QUALIFICATION_REFUSED`` whenever either list is non-empty.

Two document families come out of this phase, and they are deliberately not the same thing:

* ``qualification-verdict.json`` - this phase's own verdict over **all ten** gates.
* ``head-search-qualification.json`` and ``head-search-qualified-report.json`` - the plan's Step 5
  documents, published only when the nine **qualification** gates hold. The plan's own ordering requires
  the closed head-only report to exist before Step 6 starts the Teleop acceptance stack and the receipt
  that Step 6 writes can only be verified afterwards; the verdict is therefore ``REFUSED`` (and the CLI
  exits 2) until the acceptance receipt is presented too, and the verdict document says so explicitly in
  ``qualification_document_status``. Nothing is published from a gate that did not hold.

There is no resume, no phase selection and no existing-root mode: the run root must not exist, and a
refused qualification is repeated under a brand new run root.

Declared evidence contract for the three artefacts no producer writes yet (restart receipt, smoke
journal, Teleop acceptance receipt) is listed in :data:`DECLARED_CONTRACTS` and enforced field by field
below; those documents do not exist today, so the gates refuse by name rather than guess.
"""
