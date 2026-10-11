"""The during-qualification readback: the seventeen approved values and the four camera measurements.

The `approved_values_readback` gate (``head_search_aggregate``) consumes one document - the readback
of a qualification run - and refuses unless all seventeen approved values and the four camera measurements
were read back **under that qualification run root**, unless the readback's own values digest is the digest
the frozen promoted config carries, and unless exactly one CUDA detector was in play. Nothing produced
such a document: the values were proven once, inside the calibration run, by
``head_search_measured_readback``, but the qualification itself never queried a running
system for them. This module is that producer.

What it observes, and from which consumer
-----------------------------------------

Every one of the seventeen values is read off the **production component that consumes it**, while the one
production composition is up, and each record names that component, the expression the value was read from,
the configuration the component was constructed with and the digest of it:

===================================  ==========================================================
value                                the consumer it is read from
===================================  ==========================================================
``horizontal_fov_rad``               ``HeadSearchController(...).plan.horizontal_fov_rad``
``lock_valid_neck_rad``              ``HeadSearchController(...).plan.safe_interval_rad``
``coarse_step_rad``,                  ``HeadSearchController(...).config[...]`` - and the eleven
``search_timeout_s``,                 measured values also through
``center_deadband_px``,               ``head_search_measured_readback.observe_measured_readbacks``,
``vertical_bounds_px``,               which adds the neck port's and the stop criterion's own
``max_fine_corrections``,             attributes plus the three behavioural probes
``max_fine_total_rad``,               (deadline, freshness, skew) at the exact float boundary
``max_age_s``, ``max_skew_s``,        each component applies
``min_confidence``, ``min_area_px2``
``submit_lead_s``, ``stop_latency_s`` ``RosNeckSearchPort`` attributes (via the same readback)
``stop_velocity_rad_s``               ``RosControllerPort`` stop criterion attribute (ditto)
``tracking_iou``,                     the loaded ``HeadRgbDetector`` - the one CUDA instance this
``min_bbox_aspect``                   readback builds from the frozen weights
===================================  ==========================================================

The four camera measurements are observed **live from the running stack**, exactly as the pick-place
calibration measurement contract defines them (``config/act/pick-place-calibration-measurement-contract.json``):
``head_intrinsics_px`` from the ``/head_camera/camera_info`` the running camera plugin publishes,
``head_translation_m`` and ``head_rpy_rad`` from the ``base -> head_camera_frame`` transform the running
description publishes, and ``yaw_zero_bearing_rad`` from the bearing of that rotation's optical forward
axis. A camera measurement that the running stack does not publish is recorded as ``not_observable`` with
the reason that stopped the observation - never with the approved number restated as if it had been seen.

The documents this producer needs
---------------------------------

It is handed the same frozen artefacts the qualifier declares: the promoted production config (whose
``values`` block is the promotion of record), the approved calibration bundle (whose parameters must agree
with it, value by value, or the readback refuses with ``READBACK_BUNDLE_MISMATCH``), the frozen runtime
identity, the sealed geometry, the scene, the URDF, the MuJoCo plugin configuration, the controller
configuration, the selected weights and, through the controller configuration, the dead-man directory. It takes the exclusive-ownership
receipt, refuses unless the receipt guards exactly this run root, and starts **one** stack - the same
``RestartStack`` the production smoke and the anchor restarts own - through the restart module's own
helpers, so the qualification cannot drift into a second definition of "the stack".

The run root
------------

The gate compares the readback's ``run_root`` with the qualification run root it aggregates, character for
character, and refuses a readback taken for another run (``QUAL_AGGREGATE_VALUES_NOT_DURING_QUALIFICATION``).
The aggregate, in turn, claims its run root exclusively and refuses to resume one that exists. The
readback therefore declares the qualification run root it is taken **for** - the root the Step 1 receipt
guards, the root the aggregate claims afterwards - and writes its own evidence (this document, the teardown
proof, stdout and stderr) under the evidence root the run was given. Both roots are recorded, so a reader
can see which qualification the readback belongs to and where it was physically taken.

What refuses, and what is recorded instead
------------------------------------------

Four things are hard failures, never warnings: a stack that does not start (``READBACK_STACK_START_FAILED``),
a production component that cannot be built (``READBACK_COMPONENT_UNBUILDABLE`` /
``READBACK_DETECTOR_FAILED``), an observed value that differs from the approved one
(``READBACK_VALUE_MISMATCH`` - the observed value is recorded beside the approved one, so the refusal names
both), and a teardown that cannot be proven (``READBACK_TEARDOWN_UNPROVEN`` / ``READBACK_GPU_NOT_RELEASED``).
A camera measurement the running stack does not publish is not a failure of the run: it is recorded as
``not_observable`` with the reason, because "could not look" is evidence about this run and inventing the
number would not be.
"""
