# Offline processor: defects found on the first real pilot bag

Date: 2026-10-08

Trigger: first run of `act_offline_episode` on the pilot bag `031b82c6` (processor report `scratch/p2run-it1-*` .. `it3-*`).

Findings and changes (no rule relaxed):

1. `episode_audit.bind_row` and the readback rounded the label target `t + 0.1 s` to microseconds, while the capture mints it as the nanosecond sum. A camera stamp `4.803999999 s` made the capture's own first row fail `AUDIT_BINDING_REFERENCE_INVALID`. Both now use the nanosecond sum (`_reference_target_s`); equality stays exact. Test in `test_act_episode_audit.py`.
2. 32 of 11314 `joint_states` were stamped up to 4 ms past the latest `/clock` the bag had received (separate subscriptions); `INPUT_TIMESTAMP_FUTURE` then refused a correct stream. The live Recorder failed on the same rule first in this attempt. The replay holds such a message, in topic order, until `/clock` reaches its stamp, at most 50 ms of receipt time; a stamp `/clock` never reaches is delivered after the hold and the rule judges it. Listed in `p2-substitution.md`.
3. The offline scan now checks the camera grid and the continuity of the reference at the label instants (see the two other change documents).
4. A DIAGNOSTIC run option, `--diagnostic-camera-repair`: re-stamps camera frames within 2.5 ms of the previous frame's grid and fills up to two missing frames with copies, to look past the camera defect for further blockers. The result is labelled `DIAGNOSTIC_*`, the exit code is 5, and it is not a contract path or evidence.

Contract impact: item 1 removes a rounding mismatch; the rule itself is unchanged. The others are in the offline substitution list.

Rollback: `writer-artifacts/p2-it1-base.tar.gz` (episode_audit) and the offline package is new code.

Ledger CP: CP-3439.
