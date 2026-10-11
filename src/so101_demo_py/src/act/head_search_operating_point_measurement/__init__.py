"""The installed producers of phase 3's two inputs: the selection rule and its measurement frames.

Phase 3 of the formal head search calibration (`head_search_operating_point`) consumes two documents and
produces neither: a rule record that must exist **before** any measurement flight is admitted, and the
frames the rule is applied to. Until this module existed, neither had a producer in the installed
program (ledger HS-309), so a real `run` could not get past the CLI entry.

The two producers are deliberately separate, because the ordering is the whole point of the rule:

* `record_selection_rule_documents` writes the rule records of the domains it is asked for (the head
  domain's is the one the run declares under `--selection-rule`) from the sealed production search
  configuration alone. It refuses to write at all when the directory its measurement will own already
  exists, so a rule can never be written after the measurement it is supposed to precede; the phase-3
  module refuses the same thing a second time from the other side (`CAL_RULE_AFTER_MEASUREMENT`).
* `measure_operating_point_measurements` measures the frames the rule consumes and then has the
  installed phase 3 itself select the point of every candidate. It measures the head val split and the
  calibration episodes for the head domain, and the same two splits for the task domain, for the three
  frozen candidates: the campaign's grid of record is an 18-cell `(min_confidence, tracker.iou)` search
  (ledger HS-248/HS-249) whose two geometric values stay at the sealed production configuration's own
  `min_bbox_aspect` and `min_area_px2`, because phase 5 later refuses a bundle whose four perception
  values are not exactly the chosen point.

Two properties make the single recorded detection list re-usable for the whole grid, and both are
declared rather than assumed (`recording_settings`): the frames record detections at the grid's
**lowest** confidence and its **highest** tracker IoU. Ultralytics suppresses a box when a
higher-scoring box overlaps it by more than the threshold, so an NMS pass at a threshold at or below
the one the record was made with yields exactly what the pipeline would have produced at that
threshold, and a confidence floor above the recording floor only drops detections the floor itself
would have dropped (the argument ledger HS-265 recorded for its own selection).

The measurement reuses the gate's own code rather than a second copy of it: the val split of each
domain is the split the frozen-candidate gate verifies (`verify_split_manifest`) and each val cell is
re-measured with the gate's `_measure_static` at the candidate's declared operating point and reported
as a reference that never enters the choice. The metrics of the choice itself are the gate's episode
semantics, which phase 3 already implements (`_metrics`/`_episode_cells`): greedy nearest unused
ground-truth centre within `match_radius_px`, F1 derived from the matched counts. Where episodes are
involved the ground truth is the recorder's own convention - the mean of the cup body's segmentation
pixels in **that camera's** view (`grid/record_episodes7.py`, ledger HS-260/HS-261) - and where the
frozen dataset images are involved it is the dataset's own published truth: the pixel mean of the
instance's visible mask where the dataset publishes one, and otherwise the area centroid of its
published visible-mask polygon.

Nothing here starts ROS or commands motion: the neck angle is a simulated scene state.
"""
