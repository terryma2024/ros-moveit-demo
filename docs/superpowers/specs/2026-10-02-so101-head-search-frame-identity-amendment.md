# Amendment proposal: the promoted head-search config names two frames that do not exist

Status: **proposal for review.** No config file is edited until this is approved, because Task 14 states that any
controlled source/config change invalidates Task 13 and returns to it.

## 1. The defect, independently verified

The promoted config (Task 13 Step 3, build of record `head_search_v2.json`, digest `dfa0af9b…`) declares:

```
"frame_id": "head_camera_optical_frame"
"ray_origin_frame_id": "base_link"
```

The runtime description and the publisher say otherwise. Verified directly by reading the files (not inferred):

| name | declared where | occurrences in `assets/mujoco/act/so101.urdf` |
| --- | --- | --- |
| `head_camera_frame` | published by the camera plugin (`mujoco_plugins.yaml`, `frame_name: head_camera_frame`) | **2** |
| `head_camera_optical_frame` | config `frame_id` | **0** |
| `base_link` | config `ray_origin_frame_id` | **0** (the URDF root link is `base`) |

Consequence, re-derived by the aggregate gate and reproduced by three real `FULL_RESTART` runs (ledger HS-318):
`HeadSearchController` returns `INPUT_STALE` on **every** frame, so the search never accepts a detection and the three
restart receipts are refused (`RESTART_SEARCH_UNPROVEN`, `RESTART_LOCK_UNPROVEN`, `RESTART_TIMING_THRESHOLDS`).

Why this surfaced only now: the calibration run and the 40-scenario qualifier execute the closed loop **in process**
(renderer + detector, no TF), so they never consult these names. The restarts are the first phase that drives the
**production ROS path**, which resolves frames through TF - which is precisely what that phase exists to test.

## 2. Proposal

Correct the two names to the ones that exist, changing nothing else:

```
"frame_id": "head_camera_frame"
"ray_origin_frame_id": "base"
```

Rationale: these are **not** among the 17 approved values (they are identity/wiring keys), so the approval of the 17
values is unaffected; the change makes the config agree with the robot description and the publisher, which is what the
design assumes when it says the search consumes the production camera and TF.

**Rejected alternatives.** Renaming the URDF link or the plugin's `frame_name` instead (it would invalidate the sealed
geometry and the rendered dataset, which were produced against the current description); adding a static TF alias for
the two phantom names (it would paper over the drift and leave two names for one frame); editing the config silently
inside Task 14 (the plan forbids it and it would change the object the user's approval is bound to without a record).

## 3. What approval triggers (the plan's own rule)

"Any source/config change invalidates Task 13 and returns to it." So approval triggers a **Task 13 return**: fix the two
keys under a declared change, re-run Task 13 Steps 4 and 5 (both source suites; a new commit-stamped frozen runtime and
its identity record), re-issue the promotion record with the new config digest, and then resume Task 14's restarts and
qualification against that runtime. The approved 17 values and the approved bundle digest are **not** re-opened by this
change; only the config digest and the runtime identity move.

## 4. Questions for the reviewer

1. Is correcting the two keys to `head_camera_frame` / `base` the right fix, or is the intended frame the optical frame
   (in which case the URDF/plugin must gain it, with the seal consequences stated in section 2)?
2. Should the config, once corrected, be re-verified by `verify-promoted-config` against the **same** approved bundle
   digest, or does the config change require a new promotion record?
3. Is there any other consumer of these two keys that would be surprised by the correction?
