# Amendment proposal (revision 2): the head-search config names two frames that do not exist

Status: **proposal for review; nothing edited.** Revision 1 was rejected with three corrections (ledger HS-319), all folded in
here.

## 1. The defect, verified by reading files

The promoted config (`head_search_v2.json`, digest `dfa0af9b…`) declares `frame_id: head_camera_optical_frame` and
`ray_origin_frame_id: base_link`. The runtime disagrees:

| name | who uses it | occurrences in `assets/mujoco/act/so101.urdf` |
| --- | --- | --- |
| `head_camera_frame` | camera plugin publishes it (`mujoco_plugins.yaml`); **the production search port's own test pins both keys to it** (`test/test_act_task8_search_port.py:82`: `"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame"`) | **2** |
| `head_camera_optical_frame` | the config, and only test fixtures elsewhere | **0** |
| `base_link` | the config, and only test fixtures elsewhere | **0** (root link is `base`) |

A repository-wide search for the three names finds the two phantom names **only in the config and in test fixtures**; every
production consumer that names a frame names `head_camera_frame`. Consequence: `HeadSearchController` returns
`INPUT_STALE` on every frame, so three real `FULL_RESTART` runs accepted zero detections and their receipts were refused
(HS-318). This surfaced only now because the calibration run and the 40-scenario qualifier execute in process, without TF.

Two facts worth recording about provenance: the two keys were **already in the config before the promotion** (the promotion
changed only the model identity and 13 numerical values, HS-313), so this is **pre-existing config drift**, not something the
promotion introduced; and the drift is between the config and the code that consumes it, not between the config and the URDF
alone.

## 2. Proposal (corrected per review)

Change exactly two keys, changing nothing else:

```
"frame_id": "head_camera_frame"
"ray_origin_frame_id": "head_camera_frame"
```

Revision 1 proposed `base` for the ray origin; review corrected it - the ray origin's axes are optical, and `base` is a
separate TF target. The Task-8 search port test independently pins **both** keys to `head_camera_frame`, which is the
strongest available evidence for the intended value.

**Rejected alternatives** (unchanged from revision 1): renaming the URDF link or the plugin frame (would invalidate the sealed
geometry and the rendered dataset); adding TF aliases for the phantom names (leaves two names for one frame); editing the
config silently inside Task 14 (forbidden, and it would move the object the approval binds to without a record).

## 3. Consequence, as the review requires it

The review rejected revision 1's weaker reading and requires: **Task 13 from Step 1**, with a **fresh run root**, a **new exact
bundle approval**, and a **new promotion record**, and only then the completion of Task 14. The reason given, quoted: unchanged
numerical values do not preserve approval identity.

So the path is: fix the two keys under a declared change -> re-run the full calibration (fresh run root) -> produce a new bundle
-> **ask the user for a second exact approval of that bundle's digest** -> promote -> build a new commit-stamped frozen runtime
-> resume Task 14's restarts and qualification. The previously approved 17 numbers are expected to be identical, and that does
**not** waive the second approval.

## 4. Consumer check (review item 3) - what I found

| consumer named by the review | what the repository shows |
| --- | --- |
| legacy binding constrains the camera origin | the Task-8 search port test pins both keys to `head_camera_frame`, i.e. it expects the camera frame, not `base` |
| scenario code hardcodes the old optical-frame label | the only occurrence of `head_camera_optical_frame` outside the config is in test fixtures (`test_act_head_search_scenarios.py:139`, `test_act_head_search_camera_measurement.py:98/845`, `test_act_head_search_calibration_run_orchestration.py:441`). I could not find it hardcoded in production scenario code; if the review meant the fixtures, they must be corrected with the config so the tests stop pinning the phantom names |
| config/report validation compares the full camera identity | `test_act_task8_calibration_aggregator.py:793/810/889` compares `{"frame_id": "head_camera_frame", "ray_origin_frame_id": ...}`, i.e. the validator already expects the correct name |

## 5. Questions for the reviewer

1. Do you accept `head_camera_frame` for both keys, on the evidence of the Task-8 port test, or is there another production
   source that should decide?
2. Does the second approval need the **same 17 values presented again** (my reading of section 3), or only the new bundle digest?
3. Should the test fixtures that pin the phantom names be corrected in the same change (they would otherwise keep asserting the
   old names), and if so, is that part of the "declared change" set?
