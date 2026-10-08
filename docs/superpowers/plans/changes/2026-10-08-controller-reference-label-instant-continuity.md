# Controller reference continuity is required at the label instants

Date: 2026-10-08

Trigger: the pilot bag `031b82c6` has five arm or gripper `controller_state` gaps (arm at 67.388, 86.160 and 92.020 s, gripper at 31.512 and 86.160 s; neck 86.160 and 92.020), each one missing 2 ms frame. They are producer-side: at 67.388 the `/clock` sample is present and the arm frame is not, and the live Recorder's independent subscriber saw the same arm gap; `/clock` and `controller_state` are published with realtime `tryPublish`, which drops one message when the non-realtime side is busy. `verify_reference_continuity` required zero arm and gripper gaps anywhere in `[collection_start_s, label_cutoff_s + 0.1]`, so this producer cannot meet it although no label is affected: the grid instants of this episode are 4.804 + 0.1 k and none of the five missing frames is within 2 ms of one.

Options considered:

- A. Keep the rule and fix the producer so it never drops a `controller_state` publication. Needs a blocking publish in the realtime loop, which is exactly what a realtime publisher avoids.
- B. Require the reference at what the labels use, and count the rest.

Recommended option taken (CP-3394, CP-3439): B.

Rule (`episode_qc.verify_reference_continuity`, new `label_instants_ns` and `reference_frames_needed_ns`):

- The label instants are each row's `t + 0.1 s` for the rows from `collection_start_s` through `label_cutoff_s`.
- For each label instant the arm and gripper frame at the instant (the grid frame it matches within 1 us) and the frames one controller period (2 ms) before and after must exist. A gap removes the frames strictly between its two stamps; a gap that removes a needed frame is `REFERENCE_GAP_IN_LABEL_WINDOW` (INVALID, same code as before).
- Every other arm or gripper gap is a diagnostic count (`diagnostic_gaps`), and neck gaps stay diagnostic. A gap list that overflowed its 256 entries still cannot prove the labels clean (`REFERENCE_GAP_LIST_INCOMPLETE`).
- Labels stay bound to the command at the label instant: `build_collection_reference` still requires exactly one published frame at the instant for arm and gripper; nothing is interpolated.

The offline scan applies the same rule to the bag before processing, using the camera stamps (`camera_info`) between `reset_complete` and `normal_stop` as the row instants.

Contract impact: QC schema and codes unchanged; the rule is narrower. Data with a gap at a label instant is refused as before; data whose gaps touch no label instant is accepted with the count reported. QC reports now carry `diagnostic_gaps` in the continuity check details.

Tests (`test_b2_controller_reference.py`, `test_b2_collection_v2.py`, `test_p2_offline_processor.py`):

- a gap at a label instant, at the frame before it and at the frame after it is INVALID, for arm and gripper, including the first and last label instants and a label one nanosecond off the grid;
- an off-label gap is VALID with a diagnostic count; neck gaps stay diagnostic;
- the five gaps of the pilot bag are all off-label (window `4.803999999 .. 104.803999999`), and the real bag run confirms it (`continuity[...].gaps_touching_a_label == 0`);
- the two earlier edge tests ("a gap straddling the window edge counts") and the v2 fault fixture were changed to gaps that touch a label instant: that is the contract change.

Rollback: restore `episode_qc.py` and the two test files from `writer-artifacts/p2-camera-base.tar.gz` and `p2-qcrule-base.tar.gz`.

Ledger CP: CP-3439.
