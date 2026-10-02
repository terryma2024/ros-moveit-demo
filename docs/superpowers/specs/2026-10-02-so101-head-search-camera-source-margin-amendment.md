# Head Search camera source-age margin

This amendment replaces the camera source-age margin in the feedback-freshness amendment, revision 4 (SHA256 `21c9941493322491e9290db10cacfd9a3ba0f5ff07d817c0325205cdeca9d891`). All other formulas, measurement populations, startup and revocation rules, deadlines, ceilings and qualification requirements remain binding. The human's later instruction authorizes inline execution and self_review; exact human approval of the fresh numerical bundle remains required.

The corrected installed producer was measured in `head-stopped-bootstrap-diag-20261002T103858Z-e5941cec`. Its complete 20-second stopped CUDA window contains 4000 decision snapshots, 2000 joint messages, 200 camera images, 200 CameraInfo messages, 10000 clock messages and 200 actual detector jobs. Camera source intervals are 100 ms within the declared numerical stamp tolerance. Every original and decision remains retained, including the carry-in participants. The stack, monitor, SDK action client, TF listener and primary executor were retired; both in-process and parent graph readbacks were empty.

Camera decision source age has p99 108 ms and maximum 114 ms. Its population already includes the entire interval between exposures because it is sampled at every nominal 5 ms decision, including decisions between frames. Adding another full camera period produces 208 ms, which fails the unchanged 200 ms ceiling. The failed attempt remains REFUSED and cannot supply a provisional policy or qualification evidence.

Use the following formula instead:

`camera_max_source_age_s = camera_source_age_s.p99 + joint_source_period_s.p50`

Both operands use simulation seconds. One measured Head feedback cycle supplies the margin after the exposure interval has already been included in the decision-age population. This avoids counting a camera interval twice. For the retained diagnostic window, the joint source period is 10 ms and the proposed bound is 118 ms. This is tighter than the previous formula, and every observed camera decision age must still satisfy it. The hard ceiling remains `2 * camera_source_period_s.p50`; it is neither raised nor used to clamp a derived value. No maximum substitution, negative-age clipping, sample filtering or repeat-until-pass selection is permitted.

The joint receipt/source formulas, camera receipt-gap formula, clock receipt-gap formula, fixed 2 ms watchdog period, 10 ms reaction limit and 2 ms revoker connection deadline are unchanged. Source-period and coverage requirements, all 17 calibration names, camera receipt freshness and skew formulas, original-snapshot-before-clock ordering, capacity-one exposure handling and actual stop proof are unchanged.

Retain the formula identifier and this contract's hash in the new runtime dependencies and calibration presentation. A shadow evaluation of the retained failed window is design evidence only; it cannot repair that run or become an approved bundle. Implementation requires a new installed source closure and a fresh stopped window, followed by the formal non-resumable calibration program. The updated policy remains calibration-only until the human approves the exact fresh bundle, including its values, formulas and runtime identities. Historical approvals do not transfer to it.
