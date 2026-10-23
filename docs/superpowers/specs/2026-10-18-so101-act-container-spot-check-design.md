# SO-101 ACT: contact-policy spot checks on the container path — design and plan

Status: CONFIRMED by the human on 2026-10-18 ("确认"), with the recommended answers Q1–Q6; executing.

## Why

- The side-wrist robot model (camera rig v2) changes the compiled model and scene digests, so the contact policy must be re-derived and re-activated.
- The offline part is done: `REG/calibration/rig-side-wrist-contact-20261018T090000Z`, with 104 samples sealed and a disabled proposal (fingerprint 55ee6981…). Its thresholds are within 0.05 to 3 % of head-wrist r12.
- Human decision (2026-10-18, "按推荐的方案"): activate under CP-3394 only after the offline calibration and the live spot checks pass.
- r11/r12 ran the spot checks with `act_first_episode` / `act_diagnostic_episode run --mode preselected_target_diagnostic`. That native path was removed by 83075e656, and the container campaign accepts only a `user_activation` receipt for a formal freeze.
- Human decision: "按推荐的方案1", which means adding a diagnostic (spot-check) mode to the container campaign.

## How r11 did it (ledger CP-3531; REG/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/writer-artifacts)

- **Candidate receipt.** `act_activate_contact_policy --validation-mode offline_fit_teacher_spot_check --receipt-kind spot_check_candidate --approved-by plan:…`. `verify_activation` accepts it only in a `preselected_target_diagnostic` freeze (`contact_policy.spot_check_receipt_allowed`).
- **Nominal run.** The normal Teacher policy with collection off. It passes with Teacher COMPLETED, endpoint PASS and no oracle flag; r12 also cited phase-2 QC PASS.
- **Over-squeeze run.**
  - A separate source copy differing only in `teacher_execution_policy.yaml` `gripper_close_target_rad: -0.049`, with its own freeze; it is not a runtime knob.
  - The original plan expected a force or compression stop. Under Teacher policy v3 the process summary never stops, so CP-3531 accepted the flag reading:
    - Teacher COMPLETED;
    - `ORACLE_CUP_OVERLOAD` flagged between CLOSE_GRIPPER and VERIFY_PHYSICAL_GRASP;
    - the peaks above the frozen limits (141.4 µm and 2.249 N against 119.28 µm and 1.892 N).
- **Activation.** The final receipt (approved_by `user-standing-authorization:CP-3394`) cites both runs in free text in `approval_reference`.

## Design

1. **A spot-check plane in the container campaign.**
   - New contract kind `ACT_COLLECTION_SPOT_CHECK_RUN`:
     - the functional keys plus `collection_mode: preselected_target_diagnostic`;
     - `spot_check: nominal | over_squeeze`;
     - `worker_count == 1` and exactly one scene.
   - `act_collect_parallel --spot-check` selects it. It reuses `qualification_mode=True`, so the payload schema does not change. `--qualification` refuses this kind.
   - Retry stays forbidden, and `qualification_contract` must be null. No identifier contains `_DIAGNOSTIC`, because the repo guard forbids it in admission; names use `SPOT_CHECK`.
2. **Freeze and case inputs follow the plane.**
   - `diagnostic_episode_inputs` binds a one-row scene list in `preselected_target_diagnostic` mode and writes the frozen mode into the scopes; formal and anchor-only sets keep byte-identical hashes.
   - `case_inputs`:
     - formal and qualification planes unchanged, still formal mode and `user_activation` only;
     - the spot-check plane needs the diagnostic mode and accepts `spot_check_candidate` or `user_activation`;
     - mismatched plane/mode combinations are refused.
   - Shard side: `task_builder` and `case_artifacts` accept a formal or diagnostic frozen mode and require the scope mode to equal it. The task document carries the plane's collection mode as a cross-check.
3. **Verifier and index.**
   - The 2-tasks-per-worker owed count is skipped for the spot-check plane.
   - The index is written with `qualification: true`, so `committed_episodes` is empty.
4. **Keeping the data out.**
   - Diagnostic scopes are never export or training eligible (existing).
   - `bundle` refuses a qualification index (existing).
   - Formal admission accepts only a gate-contract qualification report (existing).
   - The over-squeeze episode is also oracle-excluded (existing).
   - New defence: `collection_qualification_recompute` requires a formal frozen mode with `user_activation`.
   - Run roots are named `act-w1s-*`; they are never sealed into or listed in a dataset.
5. **Inspect opt-in.** `act_diagnostic_episode inspect --spot-check-receipt <path>` lists a candidate receipt with approval `spot_check_candidate`, replacing r11's hand-patched candidate list. It is a flag, not a subcommand, as the guard test requires. The formal default is unchanged.
6. **Over-squeeze.** Repeat r11: a source copy with only `gripper_close_target_rad: -0.049`, its own inspect and freeze, and the campaign launched with `--teacher-execution-policy <copy>/…`. The shard takes the Teacher policy from the frozen values, so there is no new Teacher knob.
7. **Judge.** A new `cli/act_contact_spot_check.py` reads the sealed `dynamic-execute-manifest.json` (`teacher_process_summary`) and the task verdict, and writes `spot-check-verdict.json` (fingerprint, run, task-result sha, manifest sha, measured peaks and limits, PASS or FAIL).
   - **Nominal PASS:** Teacher COMPLETED, endpoint PASS, no oracle flag, summary complete, phase-2 QC PASS.
   - **Over-squeeze PASS** (the CP-3531 reading):
     - frozen close −0.049;
     - Teacher COMPLETED;
     - `ORACLE_CUP_OVERLOAD` in CLOSE_GRIPPER…VERIFY_PHYSICAL_GRASP;
     - peak force > `maximum_safe_force_n` (1.8889) or peak compression > 119.22 µm;
     - the summary thresholds equal the proposal's;
     - no `ORACLE_COLLISION` before the first overload.
8. **Activation.** If both verdicts PASS, `act_activate_contact_policy` issues the user activation, approved_by `user-standing-authorization:CP-3394`, with an `approval_reference` naming both verdict files and their sha256 and the human's decision. The receipt schema is unchanged. The result is reported afterwards.

## Decisions in this design (recommended defaults)

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Plane representation | Reuse `qualification_mode=True` plus the new contract kind; no payload schema change. |
| Q2 | Scene | One row from the debug-16 list, the same for both runs; never a formal-103 row. |
| Q3 | Over-squeeze criterion | The CP-3531 flag reading, as accepted at r11. The original stop cannot happen under Teacher policy v3. |
| Q4 | Nominal QC | Phase-2 QC PASS required; a QC fail stops and is reported. |
| Q5 | `user_activation` in the spot-check plane | Accepted too (harmless). |
| Q6 | Shard cross-check | The task document carries the collection mode; the host binding stays the primary guard. |

## Unchanged

- Data rules and thresholds.
- The formal and qualification planes: their freeze, receipts and identities are byte-identical, proven by the real-data differential readback over the 101 merged-v2 entries.
- Head-wrist behaviour.

## Plan (Sonnet writer, Opus review; tests first, fixtures only)

1. Scene binding in diagnostic sets.
2. Mode-aware case inputs.
3. Contract kind and plane.
4. Shard side.
5. Verifier, owner and index.
6. CLI, composition and admission.
7. The inspect opt-in.
8. The judge CLI.
9. The recompute defence.
10. The `w1s-spotcheck-side-wrist` template (from `w8d-debug-side-wrist`: the candidate receipt, the contract kind, the freeze mode and inspect).
11. v2 gate → images → candidate receipt → nominal campaign → source copy and over-squeeze campaign → verdicts → activation → report → resume the camera rig v2 sequence (EXP-623 debug, EXP-624 qualification, EXP-625 formal 103, TRAIN-003).
