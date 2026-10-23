"""The 40 serial qualification scenarios, their per-scenario journal and their aggregate.

The plan asks for ten condition classes times four unseen seeds, run **one at a time**:
"Legal single cup ends ``TARGET_LOCKED``; two cups end ``TARGET_AMBIGUOUS``; no cup ends
``TARGET_NOT_FOUND`` only with complete coverage; interrupted input ends the old attempt fail-closed,
proves stop, clears tracker/lock state and reacquires under a new attempt. Every scenario has zero wrong
locks, zero unsafe commands, valid timing and CUDA-only evidence."

Nothing in the frozen runtime produces that: the closest closed-loop producer,
``measure-fine-correction-episodes``, refuses every qualification seed by construction
(``declared_split_seeds`` only accepts a declared split, and its document is a fine-correction measurement
of one anchor, not a per-scenario journal), and the installed smoke proves planning *coverage* rather than
a live search. This module is the installed producer of the missing phase.

What it is:

* :func:`qualification_scenarios` reads the **tracked** partition document
  (``config/act/head-search-scenario-partitions.json``) and returns its ``qualification`` items in
  declaration order - seed, scene group, condition class and anchor. A seed of another split is refused
  (``CAL_SCENARIO_SPLIT_LEAK``): the qualification scenes are never the calibration scenes.
* :func:`expected_terminals` is the per-condition-class expectation, taken **verbatim** from the plan's
  own sentence above rather than invented here: a one-cup class passes on ``TARGET_LOCKED``, ``two_cups``
  passes on ``TARGET_AMBIGUOUS``, ``no_cup`` passes on ``TARGET_NOT_FOUND``.
* :func:`run_scenario` is the closed loop, and it is pure: the plant and the detector are injected. It
  drives the production ``HeadSearchController`` - its own bounded plan, its own freshness and skew gates,
  its own three-frame lock rule - from the item's own declared anchor, checks every commanded target
  against its corridor instead of clamping it, and returns one :func:`scenario_journal_entry`.
* :func:`check_frame_cadence` proves the 10 Hz frame contract: no duplicate, no backward and no
  undeclared gap, frames never faster than the declared frame period and never slower than the settle
  budget plus that period.
* :func:`stop_proof` proves the stop: at least three consecutive raw-feedback samples at or below the
  promoted ``stop_velocity_rad_s`` while the position error is at or below ``goal_tolerance_rad``.
* :func:`aggregate_scenarios` counts passed, failed and refused per condition class and per anchor, and
  **never** claims the qualification verdict - that belongs to the qualifier's ``aggregate`` phase, which
  this round does not implement.

What it refuses rather than fabricates (the codes are :data:`REFUSAL_CODES`):

* the whole run, before a single scene is prepared, when the exclusive-ownership gate refuses
  (:data:`CAL_SCENARIO_OWNERSHIP_REFUSED`) or the runtime of record does not hold
  (:data:`CAL_SCENARIO_RUNTIME_UNVERIFIED`);
* a scenario whose terminal outcome is not the one its condition class declares - including a **wrong
  lock**, a lock in a class that must not lock (:data:`CAL_SCENARIO_UNEXPECTED_LOCK`);
* a ``no_cup`` scenario that stopped at a bound before the sweep covered the required domain
  (:data:`CAL_SCENARIO_COVERAGE_INCOMPLETE`): "not found" is only a clean negative with complete coverage;
* a scenario whose frames violate the frame contract (:data:`CAL_SCENARIO_FRAME_CADENCE`) or whose
  terminal stop is unproven (:data:`CAL_SCENARIO_STOP_UNPROVEN`);
* a scenario that could not run to a verdict at all - the frame budget, a detector that raised, a target
  outside its corridor, a centring budget that ran out (:data:`CAL_SCENARIO_NO_VERDICT` /
  ``CAL_SCENARIO_DETECTOR_FAILED`` / ``CAL_SCENARIO_OUT_OF_CORRIDOR`` / ``CAL_SCENARIO_BUDGET_EXHAUSTED``).

A scenario that merely did not succeed - the cup was never found, a frame held two cups, the cup could
not be centred - is **recorded** with its own outcome and failure code, not raised: the run has to reach
all forty scenarios, and a refusal that stopped the run at scenario 7 would measure nothing about the
other thirty-three. Whole-run refusals are only the two preflight ones above.

The only part that touches MuJoCo, the dataset renderer, the detector or a GPU is the producer's scene
preparation, the plant and the production detector factory, and all three import their dependencies inside
the call. The detector is the production head detector (``HeadRgbDetector`` over ``YoloSegDetector``) at
the selected candidate's declared head operating point, and this producer never falls back to the CPU.
"""
