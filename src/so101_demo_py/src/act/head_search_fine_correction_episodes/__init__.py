"""The held-out fine-correction episodes: phase 6's ``fine_correction_episodes`` measurement document.

Phase 6 chooses ``max_fine_corrections`` as *the largest count a successful held-out validation episode
needed plus one recovery allowance* and ``max_fine_total_rad`` as *the largest cumulative fine correction
of those episodes plus the largest single correction observed in them*
(``head_search_search_params.compute_max_fine_corrections`` / ``compute_max_fine_total_rad``, design
section 7.1). Both numbers are properties of the **closed loop** - a scene, a bounded
sweep, a rendered frame, a detection and a correction fed back into the controller - so no open-loop
episode can carry them: the retained `episodes8` recordings are three fixed neck angles per scene, with no
correction and no success verdict at all.

What this module measures, and how:

* one **episode per held-out seed**. The scene is prepared exactly as the recorder prepared it for the
  held-out dataset (``record_episodes7.py``): the same dataset profile, the same
  ``MuJoCoDatasetRenderer._prepare`` with ``numpy.random.default_rng(seed)`` and the same
  condition-class-to-cup-count convention, so the episode looks at the scene the held-out split was
  rendered from rather than at a scene this producer invented.
* :func:`run_fine_correction_episode` is that closed loop, and it is pure: the plant and the detector are
  injected. The production :class:`so101_demo.act.search.HeadSearchController` drives it - its own bounded
  plan, its own freshness and skew gates, its own three-frame lock rule and its own fine-correction law
  (``target = neck_yaw + correction``) - and every step is checked against a declared motion corridor
  rather than clamped.
* a **fine correction** is a move the controller made on a *visible cup*: the frame's decision status is
  ``CENTER_CUP`` and the commanded target differs from the one before it. A move to the next stop of the
  bounded plan carries ``SEARCH_CUP`` and is never counted as a correction; a decision that holds the
  neck carries the same target and is counted as neither.
* the count and the magnitudes are **not this module's opinion of what the controller did**: after the
  terminal verdict they are compared against the controller's own ``fine_count`` and ``fine_angle``
  (:func:`verify_correction_consistency`), and a disagreement refuses the episode rather than recording a
  number nobody can check.

The two corridors, declared and never clamped (this is the split a single corridor needs, and the
one thing about this document a reviewer should check first):

* the **coarse corridor** is the rule of the scenario run - the intersection of the seal's
  ``required_search_domain_rad`` and its ``lock_valid_neck_rad`` - and it bounds the anchor the episode
  starts from and every stop of the bounded sweep.
* the **fine corridor** is the seal's ``lock_valid_neck_rad``: the interval the seal declares a lock
  valid in, the interval the controller's own plan clamps its stops to, and the interval
  ``compute_max_fine_total_rad`` reduces its headroom from. The production controller does **not** clamp a
  fine correction to ``required_search_domain_rad`` - that interval is the *coverage* the coarse sweep
  owes, and the seal's own ``in_frame_matrix`` says so - so bounding the fine path by the required domain
  would refuse every held-out episode of this dataset (their cup sits at the ``default`` anchor's cup
  point, which is outside the sealed pick workspace). Applying that intersection to the fine path
  would therefore not make the measurement stricter, only impossible; instead every episode records how
  far outside the required domain it locked (:func:`required_domain_excursion_rad`), and the document
  counts the excursions.

What this module refuses instead of fabricating (the codes are :data:`REFUSAL_CODES`, and the episodes
that merely did not succeed are recorded, not refused):

* a seed of a split the caller did not declare as the measured one - a calibration seed in particular -
  refuses with :data:`CAL_FINE_EPISODE_SPLIT_LEAK`, because the fine-correction path is never calibrated
  on the frames it is validated on (plan section 4 item 7; the same isolation phase 6 re-checks with
  phase 3's ``CAL_SPLIT_LEAK``);
* a commanded target or a settled neck angle outside its declared corridor
  (:data:`CAL_FINE_EPISODE_OUT_OF_CORRIDOR`), never a clamped command;
* an episode the harness's own declared measurement budget censored
  (:data:`CAL_FINE_EPISODE_BUDGET_EXHAUSTED`): an episode that hit the instrument's limit is not evidence
  that the limit was enough, so the document is refused rather than its maximum understated;
* an episode that could not run to a verdict at all - the frame budget, the controller's search timeout,
  a stale frame, a detector that raised (:data:`CAL_FINE_EPISODE_NO_VERDICT` /
  :data:`CAL_FINE_EPISODE_DETECTOR_FAILED`);
* a document in which no episode locked (:data:`CAL_FINE_EPISODE_NO_SUCCESS`), because then no
  correction count exists to bound.

The prepared scene is stepped, and the preparation is not guaranteed contact-free (the dataset profile
places the cup and the bottle by jitter and the recorder rendered without ever stepping): one held-out seed
of this campaign has its cup separated from the bottle by the solver in the first control period and pushed
out of the head camera's view. Every episode therefore records the cup's prepared position, its position at
the end of the loop and the distance between them, so such an episode is visible as a scene that moved
rather than as a search that found nothing.

An episode that *did* run to a verdict and did not lock - the cup was never found, the frame held two
cups, or the cup could not be centred - is recorded with ``succeeded: false``, its failure code and
``fine_corrections: null``. A number is never written for an episode that did not lock, and the count of
refused episodes is part of the document.

The only part that touches MuJoCo, the dataset renderer, the detector or a GPU is
:func:`prepare_episode_scene`, :class:`MujocoEpisodePlant` and the production detector factory, and all
three import their dependencies inside the call. The detector is the production head detector
(``HeadRgbDetector`` over ``YoloSegDetector``: the same class filter, aspect gate and spatial track
association the running search applies) at the selected candidate's declared head operating point, and
this measurement never falls back to the CPU.
"""
