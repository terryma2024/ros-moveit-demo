"""The closed-loop deadband lock trials: phase 6's ``deadband_candidates`` measurement document.

Phase 6 chooses ``center_deadband_px`` as *the smallest declared candidate at or above the measured
centre jitter in pixels that locks for three consecutive frames without a left-right reversal*
(``head_search_search_params.compute_center_deadband_px``, design section 7.1). The lock and the
reversal are properties of the **closed loop** - a target, a moving neck, a rendered frame, a detection
and a correction fed back into the controller - so they cannot be read off any open-loop episode. This
module runs that loop once per declared candidate in the sealed MuJoCo scene and writes the records
phase 6 consumes, or refuses rather than inventing one.

What is measured, and how:

* :func:`run_lock_trial` is the closed loop itself, and it is pure: the plant (the neck the controller
  commands) and the detector are both injected. One iteration is one control decision - the production
  :class:`so101_demo.act.search.HeadSearchController` emits a neck target, the plant steps the sealed
  scene until the declared settle rule holds, the head camera renders, the detector finds the cup, and
  the controller consumes that frame and its feedback to emit the next target. The controller is the
  production one, not a copy: its own bounded plan, its own freshness and skew gates, its own
  three-frame lock rule and its own fine-correction budget all apply.
* ``longest_locked_run_frames`` is the longest run of **consecutive frames** in which the detected cup
  is inside the candidate deadband of the principal point *and* inside the declared vertical bounds,
  with the same detection track as the frame before it. A frame with no detection, a frame outside the
  vertical bounds, and a change of track each break the run - exactly the three ways
  ``HeadSearchController`` resets its own ``lock_count``.
* ``direction_reversals`` is how many times the controller sent the neck **back the other way**: the
  number of sign changes in the sequence of the trial's commanded target moves. A single correction
  that settles, however large, is not a reversal; two corrections in opposite directions are one.
* every commanded target - the coarse plan's and every fine correction's - must lie inside the declared
  **motion corridor**, the intersection of the seal's ``required_search_domain_rad`` and its
  ``lock_valid_neck_rad``. Nothing is clamped: a target outside the corridor refuses the trial with
  :data:`CAL_DEADBAND_OUT_OF_CORRIDOR`, because clamping would command a motion the controller never
  asked for and measure that instead.

What this module refuses instead of fabricating:

* the detector produced no cup at all over the whole trial, or failed outright: no lock run exists to
  count, so the trial refuses with :data:`CAL_DEADBAND_CUP_LOST`. A *measured* absence - the cup is in
  frame but outside the candidate deadband - is not a refusal: that is the honest record that says the
  candidate is too small, and phase 6 reads it.
* a commanded stop was reached but never held (``CAL_TIMING_STOP_UNSETTLED``), never reached
  (``CAL_TIMING_SWEEP_UNSETTLED``), or the loop ran out of frames before any verdict
  (``CAL_TIMING_SWEEP_UNSETTLED``) - the timing module's own settle rule and codes, reused.
* the settle times are not the simulation clock's (``CAL_TIMING_TIME_BASE_UNVERIFIED``), proved by the
  timing module's own :func:`verify_simulation_time_base` over this trial's stops and frames.

The only part that touches MuJoCo, the detector or a GPU is :class:`MujocoClosedLoopPlant` and the
default detector factory, and both import their dependencies inside the call. The detector is the
production head detector (``HeadRgbDetector`` over ``YoloSegDetector``: the same class filter, aspect
gate and spatial track association the running search applies) at the selected candidate's declared head
operating point, and this measurement never falls back to the CPU.
"""
