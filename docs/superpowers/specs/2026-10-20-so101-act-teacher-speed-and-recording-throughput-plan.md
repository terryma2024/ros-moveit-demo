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
