# Amendment proposal (revision 3): the head-search config names frames that do not exist

Status: **proposal for review; nothing edited.** Revision 2 was rejected with one blocking correction and two clarifications
(ledger HS-320); revision 3 folds them in and corrects an error of mine.

## 0. Correction of my own claim in revision 2

Revision 2 asserted that `head_camera_optical_frame` appears "only in the config and in test fixtures". **That was wrong.**
It appears in production code:

```
src/so101_demo_py/src/act/head_search_scenarios.py:1966
            frame_id="head_camera_optical_frame",
```

Cause of my error, recorded so it is not repeated: I searched with a per-name output cap (`head -4`) and drew a
repository-wide conclusion from truncated output. The review caught it. Re-searching without a cap shows exactly this one
production occurrence and no others.

## 1. The defect, verified

The promoted config (`head_search_v2.json`, `dfa0af9b…`) declares `frame_id: head_camera_optical_frame` and
`ray_origin_frame_id: base_link`. What exists at runtime:

| name | evidence |
| --- | --- |
| `head_camera_frame` | published by the camera plugin (`mujoco_plugins.yaml`); pinned as **both** keys by the production search port's own test (`test/test_act_task8_search_port.py:82`); present **twice** in `assets/mujoco/act/so101.urdf` |
| `head_camera_optical_frame` | the config, one production hardcode (`head_search_scenarios.py:1966`), and normal-path fixtures |
| `base_link` | the config and normal-path fixtures; the URDF root link is `base` |

Consequence: `HeadSearchController` returns `INPUT_STALE` on every frame; three real `FULL_RESTART` runs accepted zero
detections and their receipts were refused (HS-318). Pre-existing drift: the two keys predate the promotion (HS-313).

## 2. Declared change set (revision 3)

The review requires the correction to include every production consumer and the normal-path fixtures, while preserving
intentional mismatch cases. The declared set is therefore:

1. **config** `head_search_v2.json`: `frame_id` and `ray_origin_frame_id` -> `head_camera_frame` (both keys; the review
   confirmed this on the production binding constraints, with the port test as corroboration);
2. **production consumer** `src/so101_demo_py/src/act/head_search_scenarios.py:1966`: the hardcoded label -> `head_camera_frame`;
3. **normal-path fixtures** that pin the phantom names (`test_act_head_search_scenarios.py:139`,
   `test_act_head_search_camera_measurement.py:98/845`, `test_act_head_search_calibration_run_orchestration.py:441`) ->
   corrected to the real names;
4. **fixtures that intentionally test a mismatch stay mismatched** - before editing I will enumerate every fixture that
   mentions either phantom name, classify each as "normal path" or "intentional negative case", and put that classification
   in the change record; a negative case may not be turned into a passing test.

Nothing else changes: no threshold, no value, no seal, no URDF link name, no plugin frame name, no TF alias.

## 3. Consequence, as the review requires it

The review requires **Task 13 from Step 1** with a **fresh run root**, **all 17 values and their required evidence presented
again** for approval of the **new exact bundle digest**, a **new promotion record**, and then **Task 14 rerun completely
under a fresh root**. Unchanged numbers do not preserve approval identity. This document does not shortcut that: after the
change, the calibration will be re-run, a new bundle produced, and the user asked to approve it again.

## 4. Questions for the reviewer

1. Is the declared change set in section 2 now complete, or is there a further production consumer I have not found?
2. For the intentional-mismatch fixtures, is a written classification (with the reason per fixture) sufficient, or does the
   review want the negative cases restated in a named test?
3. Does the second approval require the 17 values re-presented with their evidence exactly as at Step 2 (my reading), or may
   the presentation reference the previous approval for the numbers and approve only the digest?
