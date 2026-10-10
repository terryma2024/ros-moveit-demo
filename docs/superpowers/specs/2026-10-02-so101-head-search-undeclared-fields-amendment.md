# Amendment proposal: two fields the design references but no artefact declares

Status: **proposal for review, not implemented.** No value is invented, and no threshold is relaxed, until this is
approved.

## 1. What is missing, and how it surfaced

Design section 7.1 defines two of the 17 parameters in terms of quantities that **no artefact in this repository
declares**. The calibration runtime therefore refuses honestly instead of substituting a value:

| parameter | needs | declared by | observed behaviour |
| --- | --- | --- | --- |
| `vertical_bounds_px` | the image **safety edge** width `safety_margin_px` | nothing (0 hits in the installed tree; not among the 17 parameters' declaring artefacts) | `CAL_CAMERA_SAFETY_MARGIN_UNDECLARED`, CLI rc=2, field `null` (`measured_here:false`) - ledger HS-303 |
| `stop_velocity_rad_s` | the feedback **quantisation resolution** `quantisation_rad` | nothing (no joint/encoder resolution is declared anywhere) | `CAL_FEEDBACK_QUANTISATION_UNDECLARED`, rc=2; phase 7 then refuses "no finite quantisation_rad" - ledger HS-304 |

Both are honest refusals with the measurement document written and receipted. The consequence is that the bundle
cannot carry all 17 values, so `run` cannot produce a complete bundle and the approval pause cannot be reached.

## 2. Proposal A - `safety_margin_px` is **declared**, not inferred

Add one declared field to the camera configuration (`config/mujoco/camera_views.yaml` or the camera config the seal
already cites):

```yaml
image_safety_margin_fraction: <declared fraction of the shorter image edge>
```

and derive `safety_margin_px = ceil(fraction * min(image_width_px, image_height_px))` in the producer, recording the
declaring path, digest and the computed integer. Rationale: the design wants the legal pick workspace intersected
with the image safety edge, but the edge width is a **policy** value that belongs to configuration, not to a
measurement. A fraction (not a pixel count) survives resolution changes, and `ceil` keeps the bound conservative.

Rejected alternatives: inferring the edge from the workspace projection's own bounding box (circular - it would make
the margin depend on the thing it constrains); reusing any pixel-count field such as `visible_pixel_minimum` (a
different quantity with a different unit).

## 3. Proposal B - `quantisation_rad` is **derived from a declaration**, or explicitly zero

Either (B1) derive it from a declared feedback resolution - the controller configuration or the joint-state
interface the stop path consumes - recorded with the declaring path, digest and the arithmetic; or (B2), if the
controller genuinely exposes no resolution, the design states that this term is **identically zero** for this
platform and the envelope is governed by the stationary noise term plus the stopped tolerance, with that statement
recorded as the declaring artefact.

Rejected alternative: deriving it from floating-point precision or from image/pixel quantities (wrong unit, no
physical meaning).

## 4. What approval would and would not change

- It would let `vertical_bounds_px` and `stop_velocity_rad_s` be computed, unblocking the bundle and the approval pause.
- It would **not** relax `TASK_RETENTION_MARGIN`, the no-cup false-candidate gate, the stop-latency hard bound or any
  other gate; the stop-latency exceedance already recorded in HS-304 (two proofs above the declared 0.06 s, two
  proofs paced unfaithfully) remains a finding to resolve on its own.
- Whatever is approved must be written as a **declaration with provenance** (path, sha256, author, date), not as a
  constant embedded in code.

## 5. Questions for the reviewer

1. Is Proposal A's fraction-and-ceil derivation acceptable, or must the pixel margin itself be declared?
2. For Proposal B, is B1 or B2 correct for this platform, and if B1, which artefact is the declaring source?
3. Does either proposal conflict with the sealed-geometry contract (the seal must stay reproducible from its own
   declared inputs)?
