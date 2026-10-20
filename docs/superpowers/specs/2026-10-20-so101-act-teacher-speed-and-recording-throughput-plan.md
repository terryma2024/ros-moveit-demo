# SO-101 ACT: Teacher speed (item 18) and phase-1 recording throughput (item 19) — plan

Status: CONFIRMED by the human on 2026-10-20 ("3点都确认，按上面建议执行"). Analysis:
`REG/diag-delivery-20261016/teacher-dwell-20261020/report.md`.

## Findings that drive the plan

- The 64 % "dwell" is mostly slow motion: 15.5 % of rows are truly still and 48.5 % are creep.
  - MoveIt scaling is 0.03 / 0.03 in free space and 0.03 / 0.0075 for carry, and each phase has six stop-and-go segments.
- Configured waits are only 0.9 % of the episode.
- Carry has 5.9–9.7 µm of compression margin to the r10b limit (119.2 µm), so a faster carry is the only change with contact risk.
- Phase 1 runs at 89 scenes/h. The cap of 4 and the 30 s assignment gap bind together. Host headroom is large; the cap-8 failures came from real-time jitter.

## Item 18 (all LOGIC: new gate, images, identity, requalification)

**Tier 1 (sequencing only, motion unchanged; about −4.9 s per episode):**
- 18a: load the telemetry safety inputs while the physics is paused, after a phase-mark run confirms that the 3.07 s block is that call.
- 18b: precompute the pick-prefix IK horizon before the first goal. Prove it bit-identical offline against the 103 recorded horizon documents.

**Tier 2 (cumulative about −14.5 s):** new Teacher-policy keys (schema 4). Each defaults to today's value, so old freezes still verify.
- 18d: MOVE_ABOVE_OBJECT scaling 0.10 / 0.10.
- 18e: RETREAT scaling 0.10 / 0.10.
- 18f: PREPARE_OPEN gripper trajectory 1.0 s.
- Unchanged: DESCEND, MICRO_LIFT, CLOSE_GRIPPER, OPEN_GRIPPER, all waits, and the contact policy.

**Tier 3 (18g, carry acceleration):** only if the DOE passes.
- Test 16 scenes with the largest carry segments at 0.011 and then 0.015.
- Accept a level only with 0 oracle flags and p100 compression ≤ 115.5 µm.

**Not now:** 18c, 18h, 18i, 18j, 18k.

## Item 19

Qualify on the final Teacher, changing one variable at a time:
1. cap 4, gap 30 (isolates the Teacher change);
2. cap 5, gap 30;
3. cap 5 or 6, gap 20.

Do not go above cap 6. The RO envelope applies: the formal run uses at most the qualified cap and at least the qualified gap.

## Runs

The preconditions are fans at 100, a quiet host (no rollout, gate, training, or env-align apt change) and a green gate on the code that runs.

| Run | What | Pass |
| --- | --- | --- |
| R0 | Unit tests, the horizon differential, the policy loader, the v4 gate, images | green |
| R1 | Debug 16, scenes frm-000..015 paired with EXP-625, tiers 1+2, cap 4 / gap 30 | Teacher 16/16; no oracle flag; per-phase peak compression and force within EXP-625's range for the same scenes; leading rows ≤ 2.2 s; endpoint not worse |
| R2 | Contact spot checks, nominal and over-squeeze, with the new Teacher policy (contact policy unchanged) | nominal: no flag; over-squeeze: overload inside CLOSE..VERIFY |
| R3 | Carry DOE (conditional) | see tier 3 |
| R4–R6 | Qualification 40 at each step of item 19; pool two runs at the final settings | frozen rules; first-attempt INVALID ≤ 5/40 per run and ≤ 8/80 pooled; no new failure class |

## Cheap checks before coding

1. Phase marks around `load_frozen_safety`.
2. Whether the IK kernel releases the GIL.
3. A service-side YOLO trace of the 3.0 s perception mode.
4. Peak joint acceleration per carry segment from bags (speed vs acceleration).

## Non-data slot reductions (class R) → antzb queue

- Replace the chain of about 10 short Python helper processes per task (about 23 s before the recorder anchor) with a persistent worker.
- The 3.0 s perception mode: trace it and remove the quantised wait.
- Overlap perception with the Teacher start.

All are output-neutral; prove them with a debug run whose data matches.

## Order with other work

1. The limit-clamp rollouts that are running finish first.
2. Env alignment (the ai-station apt upgrade and its gate) runs when the host is idle.
3. Item 18/19 code is written meanwhile in its own worktree (`codex/so101-teacher-speed`) and merged after review.
4. Then R0–R6.
5. Then the boundary search with the final Teacher.

## Amendments after R0–R2 (2026-10-20, human decisions)

R1 (EXP-626) had Teacher 16/16 but 0/16 VALID (CP-3752).
- **Cause.** The Teacher's `reset_complete` boundary is the first record of its 2.55 s observer ring. 18a shortened the time from the end of the perception pause to the first command to about 2.1 s, so the pause now lies inside the ring. The offline clip (`scan.py`) then cannot skip it.

Decisions:
1. **Fix D (chosen over reverting 18a).** For a schema ≥ 4 Teacher policy only, the reset boundary is the first retained ring record after the last paused one. It fails closed if no such record exists. The recorder, scan, audit and all limits are unchanged, and schema 3 is byte-identical. This needs a new gate and new images, then R1 and R2 are repeated.
2. **R1 peak criterion: kept, with a control.** A same-scene schema-3 control run is added. Each EXP-626 per-phase peak (force and compression) must lie within the union range of {EXP-625, control} on the same 16 scenes, with no oracle flag and every value below the r10b limits.
3. **R1 peak criterion, revised (human decision after EXP-627).** The two-run union rule cannot be met even by an unchanged schema 3 re-run: EXP-627 alone falls outside EXP-625's range in 29 of 38 pairs. The criterion becomes one-sided with a run-to-run tolerance. Per phase and metric (peak force and peak compression):

       max(new) ≤ max(EXP-625 ∪ control) + max(|max(control) − max(EXP-625)|, floor)

   The floor is 0.02 µm for compression and 0.002 N for force. Values below the reference are allowed. No oracle flag is allowed, and every value must be below the r10b limits.
4. **Fallback A after EXP-628 (human decision).** Fix D did not take effect. The Teacher reads its transient-local observer ring 3–9 ms after the replay starts arriving, so in 11 of 12 scenes the paused records were not in it yet. The rule fired only in dbg-04.
   - **Change:** 18a's safety preload is reverted for schema 4. The load returns to its schema 3 position after pose accept, and the phase marks are kept. The fix-D code stays: it is consistent when it fires.
   - **Criterion change:** R1's "leading rows ≤ 2.2 s" criterion is dropped, because about 5 s is expected with A.
   - **What remains of tier 1:** 18b (pick-prefix precompute) only.
5. **Peak reference widened (human decision).** The one-sided rule of amendment 3 is unchanged. The reference max and the run-to-run tolerance are computed from every schema 3 run available on the same 16 scene positions: EXP-625 and EXP-627, plus EXP-623 and EXP-624 where they cover the same positions.
