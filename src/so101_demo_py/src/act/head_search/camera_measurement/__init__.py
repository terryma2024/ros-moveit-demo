"""Phase 6's ``camera_measurements`` document: the measured centre jitter and the declared margin.

Phase 6 reads five keys off this document
(``head_search_search_params.compute_center_deadband_px`` and ``compute_vertical_bounds_px``):
``horizontal_fov_rad``, ``image_width_px``, ``image_height_px``, ``centre_jitter_rad`` and
``safety_margin_px``. They do not have the same provenance, and this module keeps them apart:

* ``horizontal_fov_rad``, ``image_width_px`` and ``image_height_px`` are **declarations**: the sealed
  geometry measured them once (``horizontal_fov_rad``, ``image_width``, ``image_height``) and this
  document copies them with ``measured_here: false`` and a ``declared_by`` block naming the artefact, its
  sha256 and the key each value came from.
* ``centre_jitter_rad`` is **measured here**: the spread of the detected cup centre across repeated frames
  at a fixed, settled pose. The neck is commanded to a pose the production controller's own bounded plan
  holds, the sealed scene's position actuator holds it while the simulation steps one declared frame
  period at a time, the head camera renders, the production head detector finds the cup, and the centre
  of its box is recorded frame by frame. The statistic is the sample standard deviation (``ddof=1``) of
  the **centre column** - the axis ``lock_run`` applies ``center_deadband_px`` to - expressed as an angle
  through the sealed angular resolution ``horizontal_fov_rad / image_width_px``, which is exactly the
  ``rad_per_px`` phase 6 divides by, so ``ceil(centre_jitter_rad / rad_per_px)`` is the pixel spread that
  was measured. The document headlines the **worst case over poses** and keeps every pose's own
  distribution, its frames and its stamps beside it; the row-axis spread is recorded too, for review.
* ``safety_margin_px`` is a **declaration**, and it is declared as a **fraction of the shorter
  production image edge** in the production head-camera declaration
  ``config/perception/head_camera_yolo_seg.yaml``: this producer derives
  ``safety_margin_px = ceil(image_safety_margin_fraction * min(image_width_px, image_height_px))`` from
  that declaration and records the declaring path, its sha256 and the arithmetic, because a fraction
  survives a resolution change and the ceiling keeps the bound conservative. Nothing is inferred from the
  workspace projection the margin constrains (that would be circular) and no pixel-count field such as the
  geometry contract's ``visible_pixel_minimum`` is substituted (a different quantity with a different unit).
  When no artefact declares either form the document writes ``safety_margin_px: null`` and records the
  refusal :data:`CAL_CAMERA_SAFETY_MARGIN_UNDECLARED` beside it; it never defaults a number phase 6 would
  intersect the projected workspace with. A declared fraction outside ``(0, 0.5]`` is
  :data:`CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE`, a declaration whose own image dimensions disagree with the
  sealed geometry - or that declares both forms at once - is
  :data:`CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY`, and the pre-existing direct pixel declaration
  (``safety_margin_px``) is still read and cited unchanged. Whichever form is declared, the value is read
  from an artefact and recorded with ``measured_here: false`` and the declaring path, sha256 and key.

What is measured, and what is refused instead of fabricated:

* a frame with no detection, a frame whose detection is not a single cup, and a detector that raises are
  all :data:`CAL_CAMERA_CUP_LOST`: a centre that was not detected is never written as a zero spread, and a
  spread that was not measured is never written at all.
* a pose outside the declared motion corridor (the seal's ``required_search_domain_rad`` intersected with
  its ``lock_valid_neck_rad``) is :data:`CAL_CAMERA_POSE_OUT_OF_CORRIDOR`; nothing is clamped, because a
  clamped pose would be a pose the controller never commanded.
* a stop that was reached but never held, a stop that was never reached, and a settle time that is not the
  simulation clock's are the timing module's own refusals, reused under this module's class.

The only part that touches MuJoCo, the detector or a GPU is the injected plant (the production
:class:`so101_demo.act.head_search.deadband_measurement.plant.MujocoClosedLoopPlant`, whose module imports MuJoCo
inside its constructor) and the default detector factory (the production ``HeadRgbDetector`` over
``YoloSegDetector``, ``allow_cpu_fallback=False``); the measurement itself is a pure loop over an injected
plant and detector, so every rule above is unit-tested without MuJoCo, CUDA or ROS. No ROS node is started,
no hardware is addressed, and the scene's simulated neck is the only thing this module commands.
"""
