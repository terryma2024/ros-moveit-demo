"""The runtime sweep timing measurement: phases 6 and 7's first two measurement documents.

Phase 6's ``search_timeout_s`` is
``max_stable_stop_points * (p99_settle_s + p99_frame_s) + max_fine_corrections * control_period_s``
(design section 7.1), so it needs the settle time and the per-frame time of the bounded sweep the search
actually performs; phase 7's ``max_age_s`` is the p99.9 of the measured end-to-end frame age plus 10 ms.
Neither number exists as a declaration anywhere - they are properties of the running pipeline - so this
module measures them once, against the sealed MuJoCo scene's neck joint, and writes the two documents the
run declares under ``--search-timing`` and ``--frame-age-measurements``.

What is measured, and how:

* :class:`SettleTracker` is the declared settle rule: the neck is settled at a stop when its joint
  velocity is at or below the production ``settle_velocity_rad_s`` **for ``settle_consecutive_steps``
  consecutive control steps** and the joint is inside the production ``goal_tolerance_rad`` of the stop.
  A single quiet sample is never a settle, and a stop the neck reaches while still moving is not settled
  either.
* :class:`MujocoNeckSweepRunner` is the only part of this module that touches MuJoCo, the detector or a
  GPU, and it imports them inside the call. It walks the bounded stop points of
  ``so101_demo.act.search.HeadSearchController`` - the same plan the production search walks - inside the
  sealed scene, commanding the scene's own ``neck_yaw_joint`` position actuator at the sealed controller
  period, and produces one frame every declared frame period of **simulation** time. Every stop records
  its step count and its settle time in simulation seconds; every frame records the simulation stamps of
  its capture and of its decision and the monotonic-wall stamps of its capture, its receipt and its
  decision.
* the sweep's time base must be the MuJoCo simulation clock itself: :func:`verify_simulation_time_base`
  refuses a settle time that is not its own step count times the sealed timestep, a declared time base
  that is not ``simulation``, and a frame without simulation stamps, with
  ``CAL_TIMING_TIME_BASE_UNVERIFIED``. Timing is never inferred from a clock the sweep does not own.
* the frame age is ``decision_monotonic_s - received_monotonic_s`` in the monotonic wall-clock base the
  production controller's freshness gate uses (``HeadSearchController`` compares ``now - received_wall_s``
  against ``max_age_s``), and the p99 frame time phase 6 reads is ``decision_monotonic_s -
  frame_monotonic_s``: the whole per-frame pipeline cost, render and inference included. The simulation
  stamps of the same samples are recorded next to them so the two bases can be checked against each other
  (``sim_age_s`` is the same interval in simulation time, the ``real_time_factor`` block records the
  mapping, and the document says which base each number is in).

What this harness cannot measure yet, and will not invent:

* **no declared detector, no frame ages.** Without weights the frames cannot be timed, so
  ``p99_frame_s`` is recorded as ``null``, the frame-age and frame-contract artefacts are not written at
  all, and the timing document says ``frame_timing.measured: false``. Phase 6 then refuses that document
  with its own ``CAL_TIMEOUT_UNBOUNDED``, which is the honest outcome: a timeout cannot be bounded without
  a frame time.
* **there is no ROS transport in this harness.** The frame is rendered by the same process that decides,
  so the receipt happens immediately after the capture and the image never crosses a topic. The measured
  age is therefore the perception cost, not the perception cost plus transport; the documents say so
  (``transport_measured: false``), and the running-topic freshness measurement remains a separate
  capability.
* **the simulation is paused while a frame is produced.** The neck does not advance in wall-clock time
  while the renderer and the detector work, so ``sim_age_s`` is zero by construction and the wall-clock age
  is the whole perception cost. The recorded ``real_time_factor`` says how fast the harness actually stepped
  the sealed scene, and it is a measurement rather than an assumption: in the one real run recorded by
  ledger HS-300 it was above one, because the sealed physics steps faster than wall clock while a frame
  costs a few milliseconds. What is measured is the cost of the perception pipeline, not the residual lag
  of a pipeline coupled to a real-time clock.

This module is written so that everything except :class:`MujocoNeckSweepRunner` is a pure, independently
testable decision layer: the sweep executor is injected into
:func:`write_head_search_timing_measurement`, so the tests exercise the settle rule, the time-base proof,
every refusal and both documents without a simulator, a detector or a GPU.
"""
