# Head observation age: authorized one-second change

task_id: head-observation-age-1s-side
worktree: /data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003
branch: codex/so101-head-file-protocol-1003
source_commit: fcee299deb6953e683f81176052edd97b003b2df
evidence_root: /data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m/head-file-protocol-1003/observation-age-1s-side-20261007-214609
scope: Head file-v1 perception age default and ceiling 0.15s to 1s; current source and directed tests only.
authorization: explicit side-conversation user instruction; no parent-task continuation.
historical_evidence: immutable; no frozen configuration edits.
runtime: NONE; install_overlay: NONE; ROS_DOMAIN_ID: test-only 201; GZ_PARTITION: NONE.
status: PLANNED RED then source change then directed GREEN; package/install/live acceptance pending.

## Source and directed verification result

- OBSERVED: changed only HeadSimulationPolicy.default_document perception age and its finite ceiling to 1.0s; retained original receipt-based expiry and independent source/feedback/loss/Stop budgets. Explicit historical 0.15s policy remains valid.
- RED: policy-red001, actual rc1, 5 failed/67 passed on original default/ceiling.
- GREEN: policy-green002 154 passed/rc0; consumers-green004 280 passed/rc0, each -n8, exact /data/work/venvs/so101-v5-t004-perception/bin/python3 with NVMe tempfile/worker proofs.
- Earlier policy-green001 missed ROS message modules and had old-age controller fixture mismatch; consumers-green003 had 63 missing SO101_IPC_SOCKET_BASE fixture failures. Preserved both logs; corrected environments and scoped default-policy test configs, no unrelated production changes.
- Prospective run inputs: /data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m/head-file-protocol-1003/observation-age-1s-side-20261007-214609/inputs; both perception_max_age_s and development values.max_age_s bind at 1.0s. Original freeze023 inputs checked unchanged by SHA256.
- No install, full ordinary/package gate or live search was performed. This side task does not certify live acceptance. Current free space approximately 7.1GiB, below parent full-gate planning reserve ~11.6GB; no evidence deletion authorized in this side conversation.
- Retained: /data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m/head-file-protocol-1003/observation-age-1s-side-20261007-214609 (raw failures, green runs, provenance, patch, proposed inputs). Archived: NONE. Deletion candidates: scratch tree and owned /tmp IPC directory after readback; not deleted.
- Status: source/config change and directed verification complete; fresh installation/package/live verification pending main-thread execution. Parent ledger, goal and plan untouched.
